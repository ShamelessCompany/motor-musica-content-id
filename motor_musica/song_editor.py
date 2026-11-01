"""Editor de Temas: modificar un tema ya creado sin salir de la aplicacion.

Cada tema creado desde la app guarda un "proyecto" (JSON) con lo necesario para
recomponerlo nota por nota: el plan de la fusion o el genero + semilla del compositor,
el rack de instrumentos y la mezcla. Editar es cambiar esos parametros y volver a
renderizar; todo sigue siendo sintesis procedural (cero samples).

Ediciones disponibles:
- instrumentos por rol (rack) y volumen / silencio por pista,
- transponer (semitonos) y tempo (BPM),
- nueva melodia (otro motivo sobre la misma armonia) o nueva variacion completa.
"""

import copy
from dataclasses import asdict, dataclass, field
import random
from typing import Dict, List, Optional, Tuple

from .content_id_checks import CheckResult, check_master, check_no_samples, summarize
from .harmonic_fusion import FusionPlan, compose_fusion_events, generate_motif, plan_profile
from .instruments import DEFAULT_RACK, ROLES, gm_programs, resolve_rack
from .midi_generator import MidiTrackBundle, NoteEvent, build_bundle_from_events, generate_track_midi
from .synth_renderer import AudioMetrics, SynthConfig, render_midi_to_wav
from .theory import GENRES, PITCH_CLASS_NAMES, parse_key_name

MIN_BPM, MAX_BPM = 60, 180
MAX_TRANSPOSE = 12


@dataclass
class SongProject:
    isrc: str
    kind: str  # "fusion" | "generate"
    title: str
    bpm: int  # tempo original de la composicion
    rack: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RACK))
    volumes: Dict[str, float] = field(default_factory=lambda: {r: 1.0 for r in ROLES})
    muted: Dict[str, bool] = field(default_factory=lambda: {r: False for r in ROLES})
    transpose: int = 0
    target_bpm: Optional[int] = None
    melody_variation: int = 0
    version: int = 1
    # Compositor
    genre: Optional[str] = None
    seed: Optional[int] = None
    bars: Optional[int] = None
    # Fusion
    plan: Optional[Dict] = None
    source_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "SongProject":
        known = SongProject.__dataclass_fields__.keys()
        return SongProject(**{k: v for k, v in data.items() if k in known})

    @property
    def effective_bpm(self) -> int:
        return int(self.target_bpm or self.bpm)

    def gains(self) -> Dict[str, float]:
        return {r: 0.0 if self.muted.get(r) else float(self.volumes.get(r, 1.0)) for r in ROLES}


def apply_edits(project: SongProject, edits: Dict) -> SongProject:
    """Valida y aplica un diccionario de ediciones (lo que manda la UI).

    Devuelve un proyecto nuevo; el original queda intacto si la edicion es invalida.
    """
    project = SongProject.from_dict(copy.deepcopy(project.to_dict()))
    if "rack" in edits:
        project.rack = resolve_rack(edits["rack"], fallback=project.rack)
    for role, vol in (edits.get("volumes") or {}).items():
        if role in ROLES:
            project.volumes[role] = max(0.0, min(float(vol), 2.0))
    for role, mute in (edits.get("muted") or {}).items():
        if role in ROLES:
            project.muted[role] = bool(mute)
    if "transpose" in edits:
        project.transpose = max(-MAX_TRANSPOSE, min(int(edits["transpose"]), MAX_TRANSPOSE))
    if "bpm" in edits and edits["bpm"]:
        project.target_bpm = max(MIN_BPM, min(int(edits["bpm"]), MAX_BPM))
    if edits.get("new_melody"):
        project.melody_variation += 1
    if all(project.muted.get(r) for r in ROLES):
        raise ValueError("No se pueden silenciar las 4 pistas")
    return project


def _transpose(events: List[NoteEvent], semitones: int) -> List[NoteEvent]:
    if not semitones:
        return events
    out = []
    for e in events:
        pitch = e.pitch if e.channel == 9 else max(0, min(127, e.pitch + semitones))
        out.append(NoteEvent(pitch, e.velocity, e.start_sec, e.duration_sec, e.track_name, e.channel))
    return out


def _retime(events: List[NoteEvent], ratio: float) -> List[NoteEvent]:
    if abs(ratio - 1.0) < 1e-9:
        return events
    return [NoteEvent(e.pitch, e.velocity, e.start_sec * ratio, e.duration_sec * ratio, e.track_name, e.channel)
            for e in events]


def build_project_bundle(project: SongProject, output_mid_path: Optional[str] = None) -> MidiTrackBundle:
    """Recompone el tema con las ediciones aplicadas y devuelve el bundle MIDI."""
    bpm = project.effective_bpm
    if project.kind == "fusion":
        plan = FusionPlan.from_dict(project.plan)
        if project.melody_variation:
            # Nueva melodia: otro motivo sobre la misma forma y armonia
            plan.motif = generate_motif(random.Random(plan.seed + 7919 * project.melody_variation), plan.style)
        plan.bpm = bpm  # el compositor de fusion ya escribe en segundos al tempo pedido
        events, duration, _ = compose_fusion_events(plan)
        profile, bars = plan_profile(plan), plan.total_bars
    else:
        seed = (project.seed or 0) + 1009 * project.melody_variation
        base = generate_track_midi(genre=project.genre, bars=project.bars or 16, seed=seed)
        ratio = base.bpm / float(bpm)
        events, duration = _retime(base.events, ratio), base.duration_sec * ratio
        profile, bars = base.profile, base.bars

    events = _transpose(events, project.transpose)
    return build_bundle_from_events(
        events, profile, bpm, bars, duration,
        output_mid_path=output_mid_path, programs=gm_programs(resolve_rack(project.rack)),
    )


def current_key(project: SongProject) -> Optional[str]:
    """Tonalidad del tema con la transposicion aplicada (p. ej. 'B minor')."""
    if project.kind == "fusion" and project.plan:
        home = parse_key_name(project.plan["home_key"])
        pc, mode = home.pitch_class, home.mode
    elif project.genre in GENRES:
        profile = GENRES[project.genre]
        pc = profile.root_note % 12
        mode = "major" if "major" in profile.scale_type.value.lower() else "minor"
    else:
        return None
    return f"{PITCH_CLASS_NAMES[(pc + project.transpose) % 12]} {mode}"


def render_project(
    project: SongProject,
    output_mid_path: str,
    output_wav_path: str,
    sample_rate: int = 44100,
) -> Tuple[MidiTrackBundle, AudioMetrics, Dict[str, object]]:
    """Renderiza el proyecto editado y corre los checks de master (sonoridad, pico, cero samples)."""
    bundle = build_project_bundle(project, output_mid_path)
    metrics = render_midi_to_wav(
        bundle, output_wav_path,
        config=SynthConfig(sample_rate=sample_rate, target_lufs=-14.0, bit_depth=16),
        instruments=resolve_rack(project.rack), gains=project.gains(),
    )
    checks: List[CheckResult] = check_master(metrics) + [check_no_samples(True)]
    if project.transpose:
        note = " y se aleja de la tonalidad de las fuentes" if project.kind == "fusion" else ""
        checks.append(CheckResult(
            "tonalidad_editada", True, float(project.transpose),
            f"Transpuesto {project.transpose:+d} semitonos: el tema ahora esta en {current_key(project)}{note} (informativo)",
        ))
    return bundle, metrics, summarize(checks)


def piano_roll(bundle: MidiTrackBundle, max_notes: int = 4000) -> Dict[str, object]:
    """Notas compactas para dibujar el piano roll en la UI: [pista, nota, inicio, duracion]."""
    notes = [
        [e.track_name, e.pitch, round(e.start_sec, 3), round(e.duration_sec, 3)]
        for e in sorted(bundle.events, key=lambda e: e.start_sec)[:max_notes]
    ]
    return {"duration": round(bundle.duration_sec, 3), "bpm": bundle.bpm, "notes": notes}


def project_for_generated(isrc: str, title: str, genre: str, seed: int, bars: int, rack: Dict[str, str]) -> SongProject:
    return SongProject(isrc=isrc, kind="generate", title=title, bpm=GENRES[genre].bpm,
                       rack=resolve_rack(rack), genre=genre, seed=seed, bars=bars)


def project_for_fusion(isrc: str, title: str, plan: FusionPlan) -> SongProject:
    return SongProject(isrc=isrc, kind="fusion", title=title, bpm=plan.bpm,
                       rack=resolve_rack(plan.instruments), plan=plan.to_dict(), source_keys=list(plan.source_keys))
