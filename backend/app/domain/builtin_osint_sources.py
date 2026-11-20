"""Built-in OSINT sources (ADR-014), created or refreshed at startup by the seed.

Stable `osint-*` ids keep the seed idempotent. The seed refreshes the content from here but
never touches `is_active`, so a source the user switched off stays off.
"Freemium" sources have requires_payment=False and say so in the description.
"""

from app.domain.osint import OsintSourceFields

BUILTIN_OSINT_SOURCES: dict[str, OsintSourceFields] = {
    # breach
    "osint-hibp": OsintSourceFields(
        "Have I Been Pwned",
        "https://haveibeenpwned.com",
        "breach",
        "Busca emails en filtraciones conocidas. API opcional.",
    ),
    "osint-dehashed": OsintSourceFields(
        "DeHashed",
        "https://dehashed.com",
        "breach",
        "Búsqueda avanzada por email, usuario, IP y dominio.",
        requires_api_key=True,
        requires_payment=True,
    ),
    "osint-intelx": OsintSourceFields(
        "Intelligence X",
        "https://intelx.io",
        "breach",
        "Dark web, pastes y filtraciones históricas. Freemium.",
        requires_api_key=True,
    ),
    "osint-h8mail": OsintSourceFields(
        "h8mail",
        "https://github.com/khast3x/h8mail",
        "breach",
        "CLI: busca emails en múltiples fuentes de filtraciones.",
    ),
    # username
    "osint-sherlock": OsintSourceFields(
        "Sherlock",
        "https://github.com/sherlock-project/sherlock",
        "username",
        "CLI: busca un nombre de usuario en más de 400 redes sociales.",
    ),
    "osint-maigret": OsintSourceFields(
        "Maigret",
        "https://github.com/soxoj/maigret",
        "username",
        "CLI: más completo que Sherlock, extrae datos de los perfiles.",
    ),
    "osint-whatsmyname": OsintSourceFields(
        "WhatsMyName",
        "https://whatsmyname.app",
        "username",
        "Web: enumeración de nombres de usuario.",
    ),
    "osint-namechk": OsintSourceFields(
        "Namechk",
        "https://namechk.com",
        "username",
        "Web: disponibilidad de nombres de usuario en redes y dominios.",
    ),
    # domain
    "osint-domaintools-whois": OsintSourceFields(
        "WHOIS DomainTools",
        "https://whois.domaintools.com",
        "domain",
        "WHOIS público de dominios.",
    ),
    "osint-securitytrails": OsintSourceFields(
        "SecurityTrails",
        "https://securitytrails.com",
        "domain",
        "Histórico de DNS y WHOIS. Freemium.",
        requires_api_key=True,
    ),
    "osint-viewdns": OsintSourceFields(
        "ViewDNS",
        "https://viewdns.info",
        "domain",
        "Reverse IP, histórico DNS y WHOIS.",
    ),
    "osint-wayback": OsintSourceFields(
        "Wayback Machine",
        "https://web.archive.org",
        "domain",
        "Webs y contenidos históricos.",
    ),
    # image
    "osint-google-images": OsintSourceFields(
        "Google Images (inversa)",
        "https://images.google.com",
        "image",
        "Búsqueda inversa de imágenes.",
    ),
    "osint-yandex-images": OsintSourceFields(
        "Yandex Images",
        "https://yandex.com/images",
        "image",
        "Búsqueda inversa de imágenes; suele funcionar mejor para Europa.",
    ),
    "osint-tineye": OsintSourceFields(
        "TinEye",
        "https://tineye.com",
        "image",
        "Búsqueda inversa de imágenes.",
    ),
    "osint-exiftool": OsintSourceFields(
        "exiftool",
        "https://exiftool.org",
        "image",
        "CLI: extrae metadatos EXIF/IPTC de imágenes y documentos.",
    ),
    # code
    "osint-github-search": OsintSourceFields(
        "GitHub Search",
        "https://github.com/search",
        "code",
        "Busca emails en commits públicos.",
    ),
    "osint-git-hound": OsintSourceFields(
        "git-hound",
        "https://github.com/tillson/git-hound",
        "code",
        "CLI: emails y secretos en repositorios públicos.",
    ),
    "osint-trufflehog": OsintSourceFields(
        "Trufflehog",
        "https://github.com/trufflesecurity/trufflehog",
        "code",
        "CLI: detecta secretos expuestos.",
    ),
    # forum
    "osint-boardreader": OsintSourceFields(
        "BoardReader",
        "https://boardreader.com",
        "forum",
        "Busca usuarios en foros antiguos.",
    ),
    "osint-google-dorks": OsintSourceFields(
        "Google Dorks",
        "https://www.google.com",
        "forum",
        "Búsquedas avanzadas con operadores site:, intext:, etc.",
    ),
    # browser_fingerprint
    "osint-amiunique": OsintSourceFields(
        "Am I Unique",
        "https://amiunique.org",
        "browser_fingerprint",
        "Huella única del navegador (fingerprinting).",
    ),
    "osint-browserleaks": OsintSourceFields(
        "BrowserLeaks",
        "https://browserleaks.com",
        "browser_fingerprint",
        "IP, WebRTC, JavaScript, canvas y fuentes.",
    ),
    "osint-ipleak": OsintSourceFields(
        "IPLeak",
        "https://ipleak.net",
        "browser_fingerprint",
        "Fugas de IP por WebRTC, DNS, etc.",
    ),
    # aggregator
    "osint-spiderfoot": OsintSourceFields(
        "SpiderFoot",
        "https://github.com/smicallef/spiderfoot",
        "aggregator",
        "OSINT automatizado en más de 200 fuentes.",
    ),
    "osint-maltego": OsintSourceFields(
        "Maltego",
        "https://maltego.com",
        "aggregator",
        "Visualización gráfica de relaciones. Freemium.",
        requires_api_key=True,
    ),
    "osint-osint-framework": OsintSourceFields(
        "OSINT Framework",
        "https://osintframework.com",
        "aggregator",
        "Directorio curado de herramientas OSINT.",
    ),
}
