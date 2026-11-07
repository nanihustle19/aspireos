param(
    [Parameter(Mandatory)][string]$SdkPath,
    [Parameter(Mandatory)][string]$JdkPath,
    [string]$OutputPath = (Join-Path $PSScriptRoot '../../output/android/AspireOs.apk'),
    [string]$TestKeyPath = (Join-Path $env:LOCALAPPDATA 'BenchOS-Android/benchos-preview.jks')
)

$ErrorActionPreference = 'Stop'
$env:JAVA_HOME = (Resolve-Path -LiteralPath $JdkPath).Path
$toolsPath = Join-Path $SdkPath 'build-tools/35.0.0'
$platform = Join-Path $SdkPath 'platforms/android-35/android.jar'
$work = Join-Path ([IO.Path]::GetTempPath()) ('benchos-apk-' + [Guid]::NewGuid().ToString('N'))
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

function Invoke-BuildTool([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Android build failed in $Program (exit code $LASTEXITCODE)"
    }
}

New-Item -ItemType Directory -Path "$work/classes", "$work/dex", (Split-Path $OutputPath -Parent) -Force | Out-Null
Invoke-BuildTool "$toolsPath/aapt2.exe" @(
    'compile', '--dir', "$PSScriptRoot/res", '-o', "$work/resources.zip"
)
Invoke-BuildTool "$toolsPath/aapt2.exe" @(
    'link', '-I', $platform, '--manifest', "$PSScriptRoot/AndroidManifest.xml",
    '-o', "$work/unsigned.apk", "$work/resources.zip"
)
Invoke-BuildTool "$env:JAVA_HOME/bin/javac.exe" @(
    '--release', '8', '-encoding', 'UTF-8', '-classpath', $platform, '-d', "$work/classes",
    "$PSScriptRoot/src/com/benchos/android/MainActivity.java"
)
$classes = (Get-ChildItem -LiteralPath "$work/classes" -Recurse -Filter '*.class').FullName
Invoke-BuildTool "$toolsPath/d8.bat" (@(
    '--release', '--min-api', '26', '--lib', $platform, '--output', "$work/dex"
) + $classes)

Add-Type -AssemblyName System.IO.Compression.FileSystem
$apk = [IO.Compression.ZipFile]::Open("$work/unsigned.apk", [IO.Compression.ZipArchiveMode]::Update)
try {
    [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($apk, "$work/dex/classes.dex", 'classes.dex') | Out-Null
} finally {
    $apk.Dispose()
}
Invoke-BuildTool "$toolsPath/zipalign.exe" @('-f', '4', "$work/unsigned.apk", "$work/aligned.apk")

if (-not (Test-Path -LiteralPath $TestKeyPath)) {
    New-Item -ItemType Directory -Path (Split-Path $TestKeyPath -Parent) -Force | Out-Null
    Invoke-BuildTool "$env:JAVA_HOME/bin/keytool.exe" @(
        '-genkeypair', '-keystore', $TestKeyPath, '-storepass', 'android',
        '-alias', 'benchos-preview', '-keyalg', 'RSA', '-keysize', '2048',
        '-validity', '10000', '-dname', 'CN=AspireOs Preview'
    )
}
Invoke-BuildTool "$toolsPath/apksigner.bat" @(
    'sign', '--ks', $TestKeyPath, '--ks-pass', 'pass:android', '--ks-key-alias', 'benchos-preview',
    '--out', $OutputPath, "$work/aligned.apk"
)
Invoke-BuildTool "$toolsPath/apksigner.bat" @('verify', '--verbose', $OutputPath)
Write-Output $OutputPath
