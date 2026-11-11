// Android is on when -Pandroid is given, unless its value is "false". With no -Pandroid at all, it is
// on when local.properties has sdk.dir, which Android Studio writes when it opens the project. The file
// is gitignored and absent in the sandbox, so JVM-only builds never reach an Android repository.
// pluginManagement is compiled before the rest of this script, so it repeats the test.
// Android repositories are only consulted when the Android app is enabled.
// The JVM modules need only the Gradle Plugin Portal and Maven Central.
pluginManagement {
    val androidOn = providers.gradleProperty("android").orNull?.let { !it.equals("false", ignoreCase = true) }
        ?: File(rootDir, "local.properties").let { f -> f.isFile && f.readLines().any { it.trim().startsWith("sdk.dir") } }
    repositories {
        if (androidOn) google()
        gradlePluginPortal()
        mavenCentral()
    }
}

val androidOn: Boolean = providers.gradleProperty("android").orNull?.let { !it.equals("false", ignoreCase = true) }
    ?: File(rootDir, "local.properties").let { f -> f.isFile && f.readLines().any { it.trim().startsWith("sdk.dir") } }

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        if (androidOn) google()
        mavenCentral()
    }
}

rootProject.name = "everlang-dna"

// core:    codec, lexer/parser, affinity (mirrors everlang_standalone/everlang/biocomputing)
// predict: order-k context model over bases (the predictive analysis engine)
// fuzz:    seeded property/fuzz oracles ported from everlang_standalone/tests/fuzz_harness.py
include(":core", ":predict", ":fuzz")

// The Android app needs the Android SDK and Android Gradle Plugin (Android Studio provides both).
// Enabled by sdk.dir in local.properties (Android Studio), or explicitly with: ./gradlew -Pandroid :app:assembleDebug
// The root build.gradle.kts puts the Android Gradle Plugin on the classpath exactly when :app is included.
if (androidOn) {
    include(":app")
}
