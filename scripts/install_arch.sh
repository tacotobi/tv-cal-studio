#!/usr/bin/env bash
# Installerar det som behövs på en Arch-dator för mätning och appbygge.
# Kör själv: skriptet använder sudo och ber dig godkänna Googles SDK-licens.
set -euo pipefail

sudo pacman -S --needed argyllcms android-tools unzip zip

# JDK via mise (finns på Omarchy), utan att ändra global java-version.
mise install java@temurin-21
JAVA_HOME="$(mise where java@temurin-21)"
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"

SDK="${ANDROID_SDK:-$HOME/.local/share/android-sdk}"
if [ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
  mkdir -p "$SDK/cmdline-tools"
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/clt.zip" \
    https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
  unzip -q "$tmp/clt.zip" -d "$tmp"
  mv "$tmp/cmdline-tools" "$SDK/cmdline-tools/latest"
  rm -rf "$tmp"
fi
"$SDK/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK" \
  "platforms;android-34" "build-tools;34.0.0"

echo
echo "Klart. Dra ur och sätt i i1Display Pro så att udev-regeln ger rätt behörighet,"
echo "och kontrollera med: scripts/check_hardware.sh <tv-ip>"
