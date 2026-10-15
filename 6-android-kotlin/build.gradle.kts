// Android Gradle Plugin goes on the buildscript classpath only when settings.gradle.kts includes :app,
// so the two gates cannot drift apart. A plugins-block declaration would make every JVM-only
// build resolve com.android.application, whose marker only Google's Maven repository serves.
// app/build.gradle.kts applies it without a version. Kotlin Android stays in the plugins block.
buildscript {
    if (project.findProject(":app") != null) {
        repositories {
            google()
            mavenCentral()
        }
        dependencies {
            classpath("com.android.tools.build:gradle:8.11.1")
        }
    }
}

plugins {
    kotlin("jvm") version "2.2.0" apply false
    id("org.jetbrains.kotlin.android") version "2.2.0" apply false
}
