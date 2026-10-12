[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Lock", "Unlock")]
    [string]$Action,
    [string]$AgentSid
)

$ErrorActionPreference = "Stop"
# Utilitaire Windows de préparation du poste, distinct des étapes de traitement.
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AdministratorSid = "*S-1-5-32-544"
$SystemSid = "*S-1-5-18"
$WritableDirectories = @("cache", "outputs", "zone_depot")

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$rootBytes = [System.Text.Encoding]::UTF8.GetBytes($ProjectRoot.ToLowerInvariant())
$projectHash = [BitConverter]::ToString($sha256.ComputeHash($rootBytes)).Replace("-", "").ToLowerInvariant()
$sha256.Dispose()
$StateDirectory = Join-Path $env:ProgramData "EnqueteMultisectorielleONG\permissions\$projectHash"
$StateFile = Join-Path $StateDirectory "etat.json"

function Invoke-Icacls {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & "$env:SystemRoot\System32\icacls.exe" @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "La modification des permissions a échoué pour : $($Arguments[0])"
    }
}

function Test-Administrateur {
    $identite = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identite)
    return $principal.IsInRole(
        [System.Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Demander-Elevation {
    $sidCourant = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($Action -eq "Lock" -and -not $AgentSid) {
        $AgentSid = $sidCourant
    }

    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action $Action"
    if ($AgentSid) {
        $arguments += " -AgentSid $AgentSid"
    }
    try {
        $processus = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList $arguments `
            -Verb RunAs `
            -Wait `
            -PassThru
    }
    catch {
        Write-Error "L'élévation administrateur a été annulée ou a échoué."
        exit 1
    }
    exit $processus.ExitCode
}

function Initialiser-DossierEtat {
    New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
    Invoke-Icacls @($StateDirectory, "/inheritance:r")
    Invoke-Icacls @($StateDirectory, "/setowner", $AdministratorSid)
    Invoke-Icacls @(
        $StateDirectory,
        "/grant:r",
        "${AdministratorSid}:(OI)(CI)(F)",
        "${SystemSid}:(OI)(CI)(F)"
    )
}

function Lire-Etat {
    if (-not (Test-Path -LiteralPath $StateFile -PathType Leaf)) {
        return $null
    }

    try {
        $etat = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        throw "Le fichier d'état protégé est illisible; demander l'aide informatique."
    }
    if ($etat.Racine -ne $ProjectRoot) {
        throw "L'état de protection correspond à un autre dossier de projet."
    }
    return $etat
}

function Ecrire-Etat {
    param(
        [Parameter(Mandatory = $true)][string]$Sid,
        [Parameter(Mandatory = $true)][string]$Statut
    )

    $objet = [PSCustomObject]@{
        Racine = $ProjectRoot
        SidAgent = $Sid
        Statut = $Statut
    }
    $json = ConvertTo-Json -InputObject $objet
    [System.IO.File]::WriteAllText(
        $StateFile,
        $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Verifier-SidAgent {
    param([Parameter(Mandatory = $true)][string]$Sid)

    try {
        $null = New-Object System.Security.Principal.SecurityIdentifier($Sid)
    }
    catch {
        throw "L'identifiant du compte Windows cible est invalide."
    }
}

function Verrouiller-Projet {
    param([Parameter(Mandatory = $true)][string]$Sid)

    $identiteAgent = "*$Sid"
    Invoke-Icacls @($ProjectRoot, "/setowner", $AdministratorSid)
    Invoke-Icacls @(
        $ProjectRoot,
        "/deny",
        "${identiteAgent}:(WD,AD,D,DC,WDAC,WO)"
    )

    $fichiersRacine = Get-ChildItem -LiteralPath $ProjectRoot -Force -File
    foreach ($fichier in $fichiersRacine) {
        Invoke-Icacls @($fichier.FullName, "/setowner", $AdministratorSid)
        Invoke-Icacls @(
            $fichier.FullName,
            "/deny",
            "${identiteAgent}:(W,D,WDAC,WO)"
        )
    }

    $dossiersProteges = Get-ChildItem -LiteralPath $ProjectRoot -Force -Directory |
        Where-Object { $WritableDirectories -notcontains $_.Name }
    foreach ($dossier in $dossiersProteges) {
        Invoke-Icacls @(
            $dossier.FullName,
            "/setowner",
            $AdministratorSid,
            "/T",
            "/C"
        )
        Invoke-Icacls @(
            $dossier.FullName,
            "/deny",
            "${identiteAgent}:(OI)(CI)(W,D,DC,WDAC,WO)",
            "/T",
            "/C"
        )
    }

    foreach ($nom in $WritableDirectories) {
        $chemin = Join-Path $ProjectRoot $nom
        New-Item -ItemType Directory -Path $chemin -Force | Out-Null
        Invoke-Icacls @(
            $chemin,
            "/grant",
            "${identiteAgent}:(OI)(CI)(M)",
            "/T",
            "/C"
        )
    }

    $scriptProtection = $PSCommandPath
    Invoke-Icacls @($scriptProtection, "/setowner", $AdministratorSid)
    Invoke-Icacls @(
        $scriptProtection,
        "/deny",
        "${identiteAgent}:(W,D,WDAC,WO)"
    )
}

function Deverrouiller-Projet {
    param([Parameter(Mandatory = $true)][string]$Sid)

    $identiteAgent = "*$Sid"
    Invoke-Icacls @($ProjectRoot, "/remove:d", $identiteAgent, "/T", "/C")
    Invoke-Icacls @(
        $ProjectRoot,
        "/grant",
        "${identiteAgent}:(OI)(CI)(M)",
        "/T",
        "/C"
    )

    $scriptProtection = $PSCommandPath
    Invoke-Icacls @($scriptProtection, "/setowner", $AdministratorSid)
    Invoke-Icacls @(
        $scriptProtection,
        "/deny",
        "${identiteAgent}:(W,D,WDAC,WO)"
    )
}

if (-not (Test-Administrateur)) {
    Demander-Elevation
}

try {
    Initialiser-DossierEtat
    $etat = Lire-Etat

    if ($Action -eq "Lock") {
        if ($etat -and $etat.Statut -eq "locked") {
            Write-Host "Le code est déjà en lecture seule pour le compte agent."
            exit 0
        }
        if ($etat) {
            $AgentSid = $etat.SidAgent
        }
        if (-not $AgentSid) {
            throw "Lancer cette tâche depuis la session standard de l'agent."
        }
        Verifier-SidAgent $AgentSid
        Ecrire-Etat $AgentSid "locking"
        Verrouiller-Projet $AgentSid
        Ecrire-Etat $AgentSid "locked"
        Write-Host "Code protégé. outputs, cache et zone_depot restent accessibles en écriture."
        exit 0
    }

    if (-not $etat) {
        throw "Le projet n'a pas encore été protégé."
    }
    if ($etat.Statut -eq "unlocked") {
        Write-Host "Le code est déjà temporairement modifiable."
        exit 0
    }
    Verifier-SidAgent $etat.SidAgent
    Ecrire-Etat $etat.SidAgent "unlocking"
    Deverrouiller-Projet $etat.SidAgent
    Ecrire-Etat $etat.SidAgent "unlocked"
    Write-Host "Modification temporairement autorisée. Relancer la tâche de verrouillage après les changements."
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
