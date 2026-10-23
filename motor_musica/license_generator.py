"""Generador de Licencias y Contratos para Venta de Beats (BeatStars / Airbit Standard).

Produce contratos legales estandarizados para comercializar y licenciar instrumentales
para raperos, cantantes y creadores de contenido audiovisual.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict


class LicenseTier(str, Enum):
    BASIC_MP3 = "basic_mp3"
    PREMIUM_WAV = "premium_wav"
    TRACKOUT_STEMS = "trackout_stems"
    EXCLUSIVE_RIGHTS = "exclusive_rights"


TIER_SPECS: Dict[LicenseTier, dict] = {
    LicenseTier.BASIC_MP3: {
        "name": "Licencia Estándar MP3 (Lease)",
        "price_usd": 29.0,
        "format": "Audio MP3 (320 kbps)",
        "stream_limit": "50,000 reproducciones en Spotify/Apple Music",
        "video_limit": "1 Video Musical (Monetización no exclusiva)",
        "radio_broadcast": "No permitido",
        "for_profit_performances": "Hasta 10 presentaciones en vivo",
        "exclusive": False,
    },
    LicenseTier.PREMIUM_WAV: {
        "name": "Licencia Profesional WAV (Lease)",
        "price_usd": 49.0,
        "format": "Audio WAV Masterizado (24-bit / 44.1 kHz)",
        "stream_limit": "250,000 reproducciones en streaming",
        "video_limit": "2 Videos Musicales (YouTube / TikTok)",
        "radio_broadcast": "Hasta 2 estaciones de radio locales",
        "for_profit_performances": "Hasta 50 presentaciones en vivo",
        "exclusive": False,
    },
    LicenseTier.TRACKOUT_STEMS: {
        "name": "Licencia Ilimitada con Pistas Separadas (Stems)",
        "price_usd": 149.0,
        "format": "WAV + Pistas Multipista Separadas (Batería, Bajo 808, Acordes, Melodía)",
        "stream_limit": "1,000,000 reproducciones en streaming",
        "video_limit": "Videos ilimitados",
        "radio_broadcast": "Emisoras comerciales permitidas",
        "for_profit_performances": "Presentaciones ilimitadas",
        "exclusive": False,
    },
    LicenseTier.EXCLUSIVE_RIGHTS: {
        "name": "Cesión Exclusiva de Derechos (Full Ownership)",
        "price_usd": 499.0,
        "format": "Todos los archivos maestros (WAV, MIDI, Stems y Proyecto FL Studio)",
        "stream_limit": "Ilimitado en todas las plataformas de streaming mundiales",
        "video_limit": "Ilimitado",
        "radio_broadcast": "Ilimitado",
        "for_profit_performances": "Ilimitado",
        "exclusive": True,
    },
}


def generate_beat_license_agreement(
    beat_title: str,
    buyer_name: str,
    tier: LicenseTier,
    bpm: int,
    key_name: str,
    isrc: str,
    producer_name: str = "Shameless Music Engine",
) -> str:
    """Genera el texto legal del contrato de licencia para el comprador del beat."""
    spec = TIER_SPECS[tier]
    today_str = datetime.now(timezone.utc).strftime("%d de %B de %Y")
    
    contract = f"""# CONTRATO DE LICENCIA MUSICAL Y DERECHOS DE USO
**Tipo de Licencia:** {spec['name'].upper()}
**Fecha de Emisión:** {today_str}
**Identificador ISRC:** {isrc}

---

## 1. Partes del Contrato
- **LICENCIANTE (Productor):** {producer_name}
- **LICENCIATARIO (Artista / Comprador):** {buyer_name}
- **OBRA MUSICAL (Beat / Instrumental):** "{beat_title}"
- **Parámetros Técnicos:** {bpm} BPM | Tonalidad: {key_name}
- **Precio Pagado:** ${spec['price_usd']:.2f} USD

---

## 2. Derechos Concedidos
El Licenciante otorga al Licenciatario el derecho {'exclusivo' if spec['exclusive'] else 'no exclusivo'} e intransferible para incorporar voces grabadas sobre el instrumental y distribuir la nueva obra resultante bajo las siguientes condiciones:

1. **Límite de Distribución Digital:** {spec['stream_limit']}
2. **Archivos Entregados:** {spec['format']}
3. **Producción Audiovisual:** {spec['video_limit']}
4. **Emisión en Radio:** {spec['radio_broadcast']}
5. **Espectáculos en Vivo:** {spec['for_profit_performances']}

---

## 3. Regalías y Créditos de Autor
- **Crédito Obligatorio:** En todas las publicaciones y plataformas de streaming debe indicarse:
  *(Prod. by {producer_name})*
- **División de Regalías de Composición (Publishing):**
  - {buyer_name} (Letra y Melodía Vocal): 50%
  - {producer_name} (Composición Instrumental): 50%
- **YouTube Content ID:** {'El comprador adquiere la exclusividad y puede registrar la pista completa.' if spec['exclusive'] else 'Al ser licencia no exclusiva, el comprador NO puede registrar el beat aislado en Content ID para evitar reclamaciones a otros licenciatarios.'}

---

**Firma Digital del Licenciante:**
*{producer_name} — Shameless Company Automated Beat Engine*
"""
    return contract
