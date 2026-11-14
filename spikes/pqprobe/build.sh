#!/usr/bin/env bash
# Bygger provappen utan Gradle: aapt2 → javac → d8 → zipalign → apksigner.
# Kräver JDK 21 (mise install java@temurin-21) och Android SDK i $ANDROID_SDK
# (plattform 34, build-tools 34.0.0).
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_SDK:-$HOME/.local/share/android-sdk}"
BT="$SDK/build-tools/34.0.0"
JAR="$SDK/platforms/android-34/android.jar"
JAVA_HOME="${JAVA_HOME:-$(mise where java@temurin-21)}"
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"

# Felsökningsnyckel per dator, utanför repot. En annan dator ger en annan nyckel,
# och då måste appen avinstalleras på TV:n innan den nya installeras.
KEY="$HOME/.local/share/tv-cal-studio/debug.jks"
if [ ! -f "$KEY" ]; then
  mkdir -p "$(dirname "$KEY")"
  keytool -genkeypair -keystore "$KEY" -storepass android -keypass android -alias debug \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=tv-cal-studio debug" >/dev/null 2>&1
fi

rm -rf build && mkdir -p build/classes build/dex
"$BT/aapt2" link --manifest AndroidManifest.xml -I "$JAR" -o build/base.apk
javac -source 8 -target 8 -Xlint:-options -cp "$JAR" -d build/classes $(find src -name '*.java')
"$BT/d8" --lib "$JAR" --min-api 26 --output build/dex $(find build/classes -name '*.class')
(cd build/dex && zip -q ../base.apk classes.dex)
"$BT/zipalign" -f 4 build/base.apk build/aligned.apk
"$BT/apksigner" sign --ks "$KEY" --ks-pass pass:android --out build/pqprobe.apk build/aligned.apk
echo "build/pqprobe.apk"
