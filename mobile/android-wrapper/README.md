# AspireOs Android

The Android app opens the AspireOs website and uses its existing accounts, permissions, and candidate records. It requires Android 8.0 or newer and a running AspireOs server.

## Connect to a deployed server

Install the APK, open AspireOs, enter the HTTPS address of your deployed frontend, and tap **Connect**. Sign in with your usual AspireOs account. Tap **Server** to change the address.

## Test the local demo over USB

1. Keep the AspireOs frontend and API running on this PC on ports 3000 and 8000.
2. Enable USB debugging on the Android phone. Connect it to the PC with a data cable and approve the debugging prompt for this PC.
3. In PowerShell, run the following commands. Adjust the adb.exe path if Android platform tools are installed elsewhere.

   ```powershell
   $adb = "$env:LOCALAPPDATA/BenchOS-Android/sdk/platform-tools/adb.exe"
   & $adb devices
   & $adb reverse tcp:3000 tcp:3000
   & $adb reverse tcp:8000 tcp:8000
   & $adb install 'I:/axion/output/android/AspireOs.apk'
   ```

4. Open **AspireOs**, tap **Use local USB demo**, and sign in with your local demo account.

## Build a test APK on Windows

Install JDK 21, Android SDK Platform 35, and Android SDK Build Tools 35.0.0. From this directory, run the following command.

```powershell
.\build.ps1 -SdkPath 'C:/path/to/android/sdk' -JdkPath 'C:/path/to/jdk-21'
```

The build uses a locally generated test signing key stored outside the repository. Use a dedicated release key and distribution process for a published app.
