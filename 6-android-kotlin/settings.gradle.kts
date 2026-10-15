// Android repositories are only consulted when the Android app is enabled.
// The JVM modules need only the Gradle Plugin Portal and Maven Central.
pluginManagement {
    repositories {
        if (providers.gradleProperty("android").isPresent) google()
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        if (providers.gradleProperty("android").isPresent) google()
        mavenCentral()
    }
}

rootProject.name = "everlang-dna"

// core:    codec, lexer/parser, affinity (mirrors everlang_standalone/everlang/biocomputing)
// predict: order-k context model over bases (the predictive analysis engine)
// fuzz:    seeded property/fuzz oracles ported from everlang_standalone/tests/fuzz_harness.py
include(":core", ":predict", ":fuzz")

// The Android app needs the Android SDK and Android Gradle Plugin (Android Studio provides both).
// Enable with: ./gradlew -Pandroid :app:assembleDebug
if (providers.gradleProperty("android").isPresent) {
    include(":app")
}
