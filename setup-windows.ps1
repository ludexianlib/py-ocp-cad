$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectPath = $PSScriptRoot
$VenvPath = Join-Path $ProjectPath '.venv'
$VenvPython = Join-Path $VenvPath 'Scripts\python.exe'
$PythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
}

'import sys; assert sys.platform == "win32", "Windows Python is required"; print(sys.version)' | & $PythonPath -
if ($LASTEXITCODE -ne 0) { throw 'Windows Python check failed.' }

# Replace only the Linux environment created for this project.
if ((Test-Path -LiteralPath $VenvPath) -and -not (Test-Path -LiteralPath $VenvPython)) {
    $ConfigPath = Join-Path $VenvPath 'pyvenv.cfg'
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw 'Existing .venv is unrecognized. Move it aside and run this script again.'
    }
    $Config = Get-Content -LiteralPath $ConfigPath -Raw
    if ($Config -notmatch '(?m)^executable = /usr/bin/python3(?:\.\d+)?\s*$') {
        throw 'Existing .venv is unrecognized. Move it aside and run this script again.'
    }
    Write-Host 'Removing the Linux virtual environment...'
    Remove-Item -LiteralPath $VenvPath -Recurse -Force
}

& $PythonPath -m venv $VenvPath
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }

& $VenvPython -m pip install --only-binary=:all: --index-url https://pypi.org/simple -r (Join-Path $ProjectPath 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'OCP installation failed. Run this script again to retry.' }

& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency validation failed.' }

$Verification = @'
import math
import sys
from importlib.metadata import version

from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GProp import GProp_GProps

assert sys.platform == "win32"
assert sys.prefix != sys.base_prefix
shape = BRepPrimAPI_MakeBox(1.0, 2.0, 3.0).Shape()
assert BRepCheck_Analyzer(shape).IsValid()
properties = GProp_GProps()
BRepGProp.VolumeProperties_s(shape, properties)
assert math.isclose(properties.Mass(), 6.0, rel_tol=1e-12)
print("Python:", sys.executable)
print("OCP:", version("cadquery-ocp"))
print("VTK:", version("vtk"))
print("Verification passed: valid box, volume =", properties.Mass())
'@

$Verification | & $VenvPython -
if ($LASTEXITCODE -ne 0) { throw 'OCP geometry verification failed.' }

Write-Host 'Windows environment ready. Activate it with: .\.venv\Scripts\Activate.ps1'
