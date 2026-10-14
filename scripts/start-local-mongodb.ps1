$ErrorActionPreference = 'Stop'
$atlasRoot = Split-Path -Parent $PSScriptRoot
$atlasServerRoot = Join-Path $atlasRoot 'tmp/mongodb/server'
$atlasBinary = Get-ChildItem -LiteralPath $atlasServerRoot -Filter mongod.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if (-not $atlasBinary) {
    throw 'Portable MongoDB not found. Install MongoDB or use docker compose up -d mongodb.'
}
$atlasData = Join-Path $atlasRoot 'data/mongodb'
$atlasLog = Join-Path $atlasRoot 'tmp/mongodb/mongod.log'
New-Item -ItemType Directory -Path $atlasData -Force | Out-Null
& $atlasBinary --bind_ip 127.0.0.1 --port 27017 --dbpath $atlasData --logpath $atlasLog --logappend
