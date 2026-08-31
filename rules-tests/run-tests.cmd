@echo off
rem Runs the Firestore rules tests against the emulator.
rem Requires Java 11+; pass the JRE bin dir as %1 to prepend to PATH.
if not "%~1"=="" set "PATH=%~1;%PATH%"
cd /d "%~dp0"
call npx firebase emulators:exec --only firestore --project gabay-ofw-rules-test "node node_modules/mocha/bin/mocha.js --timeout 20000 firestore.rules.test.mjs"
