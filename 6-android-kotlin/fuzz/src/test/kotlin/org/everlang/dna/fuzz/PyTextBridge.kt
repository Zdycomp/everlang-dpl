package org.everlang.dna.fuzz

import java.lang.reflect.InvocationTargetException
import java.lang.reflect.Method

/**
 * Python str semantics (str.upper(), str.isspace(), and the whitespace removal of str.split()), taken from
 * core's PyText, so the oracle uses the same predicate as the codec under test.
 *
 * PyText is internal to the core module, so this module cannot name it at compile time. It is loaded once
 * by reflection. javap -p shows its public methods without JVM name mangling: upper(String), removeSpace(String)
 * and isSpace(int) on the static INSTANCE. If the lookup fails, the object initializer throws. Nothing falls back
 * to java.lang.Character or String.uppercase(), because those disagree with CPython.
 *
 * The oracle therefore agrees with core on whitespace and case by construction. The independent CPython check
 * for those is core's BmpParityTest, which compares every BMP code point with a CPython-generated table.
 */
internal object PyTextBridge {
    private const val CLASS_NAME = "org.everlang.dna.PyText"

    private val target: Any
    private val upperMethod: Method
    private val removeSpaceMethod: Method
    private val isSpaceMethod: Method

    init {
        val cls = Class.forName(CLASS_NAME)
        target = cls.getField("INSTANCE").get(null)
        upperMethod = cls.getMethod("upper", String::class.java)
        removeSpaceMethod = cls.getMethod("removeSpace", String::class.java)
        isSpaceMethod = cls.getMethod("isSpace", Int::class.javaPrimitiveType!!)
    }

    /** str.upper(). */
    fun upper(text: String): String = call(upperMethod, text) as String

    /** "".join(text.split()): every str.isspace() code point is removed. */
    fun removeSpace(text: String): String = call(removeSpaceMethod, text) as String

    /** str.isspace() for one code point. */
    fun isSpace(codePoint: Int): Boolean = call(isSpaceMethod, codePoint) as Boolean

    private fun call(method: Method, argument: Any): Any? =
        try {
            method.invoke(target, argument)
        } catch (e: InvocationTargetException) {
            throw e.targetException
        }
}
