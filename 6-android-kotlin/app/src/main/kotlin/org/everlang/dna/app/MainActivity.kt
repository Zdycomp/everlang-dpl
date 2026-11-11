package org.everlang.dna.app

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.text.Editable
import android.text.TextWatcher
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import org.everlang.dna.BinarySequencer
import org.everlang.dna.predict.evaluateBytes
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.Locale

/**
 * One screen. The source is the typed text (UTF-8) or the last opened file. Sequence encodes the
 * source bytes as a DNA strand. Predict measures an order-8 context model over them.
 *
 * Work runs on a plain Thread. That Thread holds no Activity: it posts its result to the main
 * thread, and the [Session] hands the result to whichever Activity is attached then, or keeps it
 * until one is. The Session survives a configuration change through onRetainNonConfigurationInstance.
 * Buttons stay disabled while a job runs, including in a recreated Activity.
 */
class MainActivity : Activity() {

    private lateinit var input: EditText
    private lateinit var sourceLabel: TextView
    private lateinit var output: TextView
    private lateinit var sequenceButton: Button
    private lateinit var predictButton: Button
    private lateinit var openButton: Button

    private lateinit var session: Session

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // The layout always contains these views. findViewById is annotated @Nullable in the framework.
        input = findViewById<EditText>(R.id.input)!!
        sourceLabel = findViewById<TextView>(R.id.source_label)!!
        output = findViewById<TextView>(R.id.output)!!
        sequenceButton = findViewById<Button>(R.id.button_sequence)!!
        predictButton = findViewById<Button>(R.id.button_predict)!!
        openButton = findViewById<Button>(R.id.button_open)!!

        sequenceButton.setOnClickListener { startSequence() }
        predictButton.setOnClickListener { startPredict() }
        openButton.setOnClickListener { openFile() }

        @Suppress("DEPRECATION")
        val retained = lastNonConfigurationInstance as? Session
        session = retained ?: Session().also { restoreAfterProcessDeath(it, savedInstanceState) }

        // Attach after the views exist. A result that finished while no Activity was attached is applied now.
        session.host = this
        session.pending?.let {
            session.pending = null
            it(this)
        }
        render()
    }

    override fun onPostCreate(savedInstanceState: Bundle?) {
        super.onPostCreate(savedInstanceState)
        // Registered only now. onRestoreInstanceState has already set the EditText text, and a watcher
        // registered earlier would clear the opened file on every restore.
        input.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                // Typing after a file was opened makes the typed text the source again.
                if (session.fileBytes != null) {
                    session.fileBytes = null
                    updateSourceLabel()
                }
            }
        })
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        // A Bundle cannot hold a 16 MiB file, so after process death only its name is kept, to report it.
        outState.putBoolean(KEY_HAD_FILE, session.fileBytes != null)
        outState.putString(KEY_FILE_NAME, session.fileName)
        outState.putCharSequence(KEY_OUTPUT, session.output)
    }

    @Suppress("DEPRECATION")
    override fun onRetainNonConfigurationInstance(): Any = session

    override fun onDestroy() {
        if (::session.isInitialized && session.host === this) session.host = null
        super.onDestroy()
    }

    private fun startSequence() {
        val app = applicationContext
        val file = session.fileBytes
        val text = input.text.toString()
        runInBackground(
            work = { sequenceReport(app, file ?: text.toByteArray(Charsets.UTF_8)) },
            done = { a, result -> a.showOutput(result.getOrElse { a.failureText(it) }) },
        )
    }

    private fun startPredict() {
        val app = applicationContext
        val file = session.fileBytes
        val text = input.text.toString()
        runInBackground(
            work = { predictReport(app, file ?: text.toByteArray(Charsets.UTF_8)) },
            done = { a, result -> a.showOutput(result.getOrElse { a.failureText(it) }) },
        )
    }

    @Suppress("DEPRECATION")
    private fun openFile() {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType("*/*")
        try {
            startActivityForResult(intent, REQUEST_OPEN_FILE)
        } catch (e: ActivityNotFoundException) {
            showOutput(getString(R.string.no_file_picker))
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode == REQUEST_OPEN_FILE && resultCode == RESULT_OK && uri != null) {
            loadFile(uri)
        }
    }

    private fun loadFile(uri: Uri) {
        val app = applicationContext
        runInBackground(
            work = { LoadedFile(displayName(app, uri), readBounded(app, uri)) },
            done = { a, result -> a.onFileLoaded(result) },
        )
    }

    private fun onFileLoaded(result: Result<LoadedFile>) {
        result.fold(
            onSuccess = { loaded -> showLoaded(loaded) },
            onFailure = { e -> showOutput(failureText(e)) },
        )
    }

    private fun showLoaded(loaded: LoadedFile) {
        val bytes = loaded.bytes
        if (bytes == null) {
            showOutput(getString(R.string.file_too_large, MAX_FILE_BYTES / (1024 * 1024)))
            return
        }
        session.fileBytes = bytes
        session.fileName = loaded.name
        updateSourceLabel()
        showOutput(getString(R.string.file_loaded, loaded.name, bytes.size))
    }

    /**
     * Runs [work] on a worker thread, then calls [done] on the UI thread. [done] receives the Activity
     * attached at that moment, so a result is not lost to a configuration change. Only one job runs at a
     * time: while one is busy, this returns without starting another.
     */
    private fun <T> runInBackground(work: () -> T, done: (MainActivity, Result<T>) -> Unit) {
        val s = session
        if (s.busy) return
        s.busy = true
        setBusy(true)
        showOutput(getString(R.string.working))
        val mainThread = Handler(Looper.getMainLooper())
        Thread {
            val result = runCatching(work)
            mainThread.post {
                s.deliver { attached ->
                    s.busy = false
                    attached.setBusy(false)
                    done(attached, result)
                }
            }
        }.start()
    }

    /** Shows the session's state in this Activity: the busy buttons, the source label and the output. */
    private fun render() {
        setBusy(session.busy)
        updateSourceLabel()
        output.text = session.output ?: getString(R.string.output_idle)
    }

    private fun showOutput(text: CharSequence) {
        session.output = text
        output.text = text
    }

    private fun setBusy(busy: Boolean) {
        sequenceButton.isEnabled = !busy
        predictButton.isEnabled = !busy
        openButton.isEnabled = !busy
    }

    private fun updateSourceLabel() {
        val bytes = session.fileBytes
        sourceLabel.text = if (bytes == null) {
            getString(R.string.source_typed)
        } else {
            getString(R.string.source_file, session.fileName, bytes.size)
        }
    }

    private fun failureText(e: Throwable): String = when (e) {
        is OutOfMemoryError -> getString(R.string.out_of_memory)
        is IOException -> getString(R.string.file_open_failed)
        else -> getString(R.string.failed, e.message ?: e.javaClass.simpleName)
    }
}

/**
 * What survives a configuration change: the opened file, the last output, whether a job runs, and a
 * result that finished while no Activity was attached. [host] is set while an Activity is attached and
 * cleared in its onDestroy, so the Session never keeps a destroyed Activity reachable.
 */
private class Session {
    var host: MainActivity? = null
    var fileBytes: ByteArray? = null
    var fileName: String = ""
    var output: CharSequence? = null
    var busy: Boolean = false
    var pending: ((MainActivity) -> Unit)? = null

    fun deliver(action: (MainActivity) -> Unit) {
        val attached = host
        if (attached != null) action(attached) else pending = action
    }
}

/** Restores the output after process death. The file itself cannot be kept, so the output says so. */
private fun MainActivity.restoreAfterProcessDeath(session: Session, saved: Bundle?) {
    session.output = when {
        saved == null -> getString(R.string.output_idle)
        saved.getBoolean(KEY_HAD_FILE, false) -> getString(R.string.file_not_kept, saved.getString(KEY_FILE_NAME).orEmpty())
        else -> saved.getCharSequence(KEY_OUTPUT) ?: getString(R.string.output_idle)
    }
}

private class LoadedFile(val name: String, val bytes: ByteArray?)

/** Runs on the worker thread. Reads only the application context, never an Activity. */
private fun sequenceReport(app: Context, data: ByteArray): String {
    if (data.isEmpty()) return app.getString(R.string.empty_input)
    if (data.size > SEQUENCE_MAX_BYTES) {
        return app.getString(
            R.string.sequence_too_large,
            SEQUENCE_MAX_BYTES / 1024,
            MAX_FILE_BYTES / (1024 * 1024),
        )
    }
    val report = BinarySequencer().sequence(data)
    val shown = report.dna.take(STRAND_PREVIEW_CHARS)
    val hidden = report.dna.length - shown.length
    val strand = if (hidden > 0) app.getString(R.string.strand_truncated, shown, hidden) else shown
    val gc = report.gcContent?.let { fmt("%.1f%%", it * 100.0) } ?: app.getString(R.string.not_available)
    return app.getString(
        R.string.sequence_report,
        report.byteCount,
        report.dna.length,
        strand,
        gc,
        report.codons.size,
        app.getString(if (report.roundTrip) R.string.yes else R.string.no),
    )
}

/** Runs on the worker thread. Reads only the application context, never an Activity. */
private fun predictReport(app: Context, data: ByteArray): String {
    if (data.isEmpty()) return app.getString(R.string.empty_input)
    if (data.size > MAX_FILE_BYTES) {
        return app.getString(R.string.predict_too_large, MAX_FILE_BYTES / (1024 * 1024))
    }
    val r = evaluateBytes(data, PREDICT_ORDER)
    return app.getString(
        R.string.predict_report,
        r.bases,
        fmt("%.4f", r.bitsPerBase),
        fmt("%.1f", r.baselineBitsPerBase),
        fmt("%.2f%%", r.top1Accuracy * 100.0),
    )
}

/**
 * Runs on the worker thread. Returns the file's display name. Providers may return null or an empty
 * name, so those fall back to the last path segment.
 */
private fun displayName(app: Context, uri: Uri): String {
    app.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            val name: String? = if (column >= 0) cursor.getString(column) else null
            if (name != null && name.isNotBlank()) return name
        }
    }
    return uri.lastPathSegment ?: app.getString(R.string.file_fallback_name)
}

/**
 * Runs on the worker thread. Reads [uri] up to [MAX_FILE_BYTES] and stops at the first byte past the limit.
 * Returns null when the file is larger, so an oversized file is never held in memory.
 */
private fun readBounded(app: Context, uri: Uri): ByteArray? {
    val stream = app.contentResolver.openInputStream(uri)
        ?: throw IOException("openInputStream returned null")
    return stream.use { source ->
        val out = ByteArrayOutputStream()
        val buffer = ByteArray(READ_BUFFER_BYTES)
        var refused = false
        var n = source.read(buffer)
        while (n >= 0) {
            if (out.size() + n > MAX_FILE_BYTES) {
                refused = true
                break
            }
            out.write(buffer, 0, n)
            n = source.read(buffer)
        }
        if (refused) null else out.toByteArray()
    }
}

private fun fmt(pattern: String, vararg args: Any?): String = String.format(Locale.US, pattern, *args)

private const val REQUEST_OPEN_FILE = 1
private const val MAX_FILE_BYTES = 16 * 1024 * 1024
private const val READ_BUFFER_BYTES = 64 * 1024

/** Sequence builds one token and one pair object per base (four per byte), so its input is capped. */
private const val SEQUENCE_MAX_BYTES = 128 * 1024
private const val STRAND_PREVIEW_CHARS = 400
private const val PREDICT_ORDER = 8

private const val KEY_HAD_FILE = "had_file"
private const val KEY_FILE_NAME = "file_name"
private const val KEY_OUTPUT = "output"
