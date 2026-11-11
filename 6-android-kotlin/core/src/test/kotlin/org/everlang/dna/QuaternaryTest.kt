package org.everlang.dna

import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals

/** Mirrors the QuaternaryTranslationLayer cases of everlang_standalone/tests/test_biocomputing.py. */
class QuaternaryTest {
    private fun bytes(vararg v: Int) = ByteArray(v.size) { v[it].toByte() }

    @Test
    fun roundTripAllByteValues() {
        val data = ByteArray(256) { it.toByte() }
        assertContentEquals(data, Quaternary.dnaToBytes(Quaternary.bytesToDna(data)))
        for (v in 0 until 256) {
            val one = bytes(v)
            assertContentEquals(one, Quaternary.dnaToBytes(Quaternary.bytesToDna(one)))
        }
    }

    @Test
    fun baseMapping() {
        assertEquals("ATCG", Quaternary.bytesToDna(bytes(0b00011011)))
        assertEquals("AAAA", Quaternary.bytesToDna(bytes(0x00)))
        assertEquals("GGGG", Quaternary.bytesToDna(bytes(0xFF)))
        assertEquals("TTTT", Quaternary.bytesToDna(bytes(0b01010101)))
        assertEquals("CCCC", Quaternary.bytesToDna(bytes(0b10101010)))
    }

    @Test
    fun fourBasesPerByte() {
        for (n in listOf(0, 1, 5, 32)) assertEquals(4 * n, Quaternary.bytesToDna(ByteArray(n)).length)
    }

    // Not ported: the Python test that clamps out-of-range ints (-5, 300, 256, -1) cannot be written
    // against ByteArray, which holds only -128..127 and always encodes exactly one byte.

    @Test
    fun dnaToBytesIgnoresSpacesAndCase() {
        assertContentEquals(bytes(0b00011011), Quaternary.dnaToBytes("atcg"))
        assertContentEquals(bytes(0b00011011, 0), Quaternary.dnaToBytes("AT CG AA AA"))
    }

    @Test
    fun dnaToBytesDropsTrailingIncompleteByte() {
        assertContentEquals(bytes(0b00011011), Quaternary.dnaToBytes("ATCGA"))
        assertContentEquals(ByteArray(0), Quaternary.dnaToBytes("ATC"))
        assertContentEquals(ByteArray(0), Quaternary.dnaToBytes(""))
    }

    @Test
    fun dnaToBytesAppliesFullUppercaseMappingBeforeFiltering() {
        assertContentEquals(ByteArray(0), Quaternary.dnaToBytes("\u00DF"))
        assertContentEquals(bytes(0x40), Quaternary.dnaToBytes("\uFB05AAA"))
        assertContentEquals(bytes(0x00), Quaternary.dnaToBytes("\u1E9AAAA"))
        assertContentEquals(bytes(0x00), Quaternary.dnaToBytes("\u0131AAAA"))
    }
}
