# Instalador de Kimi Memory (PowerShell / Windows)
# Asume que se ejecuta desde el directorio del repositorio clonado.

$RepoDir = (Resolve-Path -Path $PSScriptRoot).Path
$PluginDir = "$env:USERPROFILE\.kimi-code\plugins\kimi-memory"
$SkillDir = "$env:USERPROFILE\.kimi\skills\kimi-memory"
$McpConfigDir = "$env:USERPROFILE\.kimi"
$McpConfig = "$McpConfigDir\mcp.json"

Write-Host "== Kimi Memory ==" -ForegroundColor Cyan
Write-Host "Repo:   $RepoDir" -ForegroundColor Cyan
Write-Host "Plugin: $PluginDir" -ForegroundColor Cyan
Write-Host "Skill:  $SkillDir" -ForegroundColor Cyan

# Verificar Python
$Python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { $null }
if (-not $Python) {
    Write-Error "Error: se requiere Python 3.10+"
    exit 1
}

# Preferir ruta absoluta
$PythonAbs = (Get-Command $Python).Source

Write-Host "Python: $PythonAbs"

# Verificar FTS5
& $Python -c "import sqlite3; conn=sqlite3.connect(':memory:'); conn.execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('SQLite FTS5: OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "SQLite FTS5 no está disponible"
    exit 1
}

# Copiar plugin
Write-Host "Copiando plugin a $PluginDir..."
New-Item -ItemType Directory -Force -Path $PluginDir | Out-Null
Copy-Item -Path "$RepoDir\memory_mcp.py" -Destination "$PluginDir\memory_mcp.py" -Force
Copy-Item -Path "$RepoDir\test_mcp.py" -Destination "$PluginDir\test_mcp.py" -Force
Copy-Item -Path "$RepoDir\kimi.plugin.json" -Destination "$PluginDir\kimi.plugin.json" -Force

# Copiar skill
Write-Host "Copiando skill a $SkillDir..."
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
Copy-Item -Path "$RepoDir\skills\kimi-memory\SKILL.md" -Destination "$SkillDir\SKILL.md" -Force

# Crear ~/.kimi/mcp.json si no existe
New-Item -ItemType Directory -Force -Path $McpConfigDir | Out-Null
if (-not (Test-Path $McpConfig)) {
    '{"mcpServers": {}}' | Set-Content -Path $McpConfig -Encoding UTF8
}

# Actualizar ~/.kimi/mcp.json
$MemoryDb = "$env:USERPROFILE\.kimi-code\memory.db"
$Config = Get-Content -Path $McpConfig -Raw | ConvertFrom-Json
if (-not $Config.mcpServers) {
    $Config | Add-Member -NotePropertyName mcpServers -NotePropertyValue @{} -Force
}
$Config.mcpServers | Add-Member -NotePropertyName "kimi-memory" -NotePropertyValue ([PSCustomObject]@{
    command = $PythonAbs
    args = @("-u", "$PluginDir\memory_mcp.py")
    env = [PSCustomObject]@{ KIMI_MEMORY_DB = $MemoryDb }
}) -Force

$Config | ConvertTo-Json -Depth 10 | Set-Content -Path $McpConfig -Encoding UTF8

Write-Host ""
Write-Host "Instalación lista. Configuración MCP guardada en: $McpConfig" -ForegroundColor Green
Write-Host "Para activar el plugin en Kimi Code CLI ejecuta:" -ForegroundColor Green
Write-Host "  /plugins install $PluginDir"
Write-Host "  /plugins reload"
Write-Host ""
Write-Host "Para probar el servidor MCP manualmente:" -ForegroundColor Green
Write-Host "  $Python $PluginDir\test_mcp.py"
Write-Host ""
Write-Host "Nota: reinicia Kimi Code CLI para que reconozca el servidor MCP." -ForegroundColor Yellow
