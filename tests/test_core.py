from pathlib import Path
import numpy as np

from app.core.edl import automatic_target_duration, edl_duration, make_edl, validate_highlights
from app.core.effects import filters_for_effects, validate_effect, windowed_video_filtergraph
from app.core.captions import build_srt, srt_timestamp, _caption_chunks
from app.core.gameplay import normalized_to_pixels, detect_dead_zones, detect_events, detect_outcome_candidates, sanitize_activity, save_debug_frames, _round_result_score
from app.core.gameplay import build_activity_score
from app.core.audio import _times, audio_features_are_finite
from app.core.highlights import group_events
from app.core.highlights import build_highlights, style_highlight_settings
from app.core.layout import validate_layout
from app.core.local_llm import LocalLLM
from app.core.jobs import JobManager
from app.core.project import source_signature
from app.core.project import append_log
from app.core import project as project_module
from app.core.project import recent_projects
from app.core import assets as assets_module
from app.core.probe import _ratio
from app.core.ranking import score_event
from app.core.renderer import encoder_options, segment_command, subtitle_style
from app.core.output import fit_output_crops, normalize_output_settings, output_size
from app.core.captions import read_srt_entries, write_manual_srt
from app.core.updates import _version
from app.core.verify import expected_edl_duration
from app.core.speech import transcript_events
from app.core.transcription import FasterWhisperTranscriber
from app.main import health


def test_fps_rational_parsing():
    assert abs(_ratio("60000/1001") - 59.94005994) < .0001


def test_normalized_coordinates():
    assert normalized_to_pixels({"x": .1, "y": .2, "width": .5, "height": .25}, 1920, 1080) == {"x": 192, "y": 216, "width": 960, "height": 270}


def test_group_events():
    events = [{"start": 10, "end": 11, "type": "combat"}, {"start": 14, "end": 15, "type": "kill"}, {"start": 30, "end": 31, "type": "combat"}]
    assert [len(x) for x in group_events(events, 5)] == [2, 1]


def test_dead_zone_separates_nearby_events():
    events = [{"start": 10, "end": 11, "type": "combat"}, {"start": 14, "end": 15, "type": "reaction"}]
    zones = [{"start": 11, "end": 14, "type": "dead_zone"}]
    assert [len(group) for group in group_events(events, 5, zones)] == [1, 1]


def test_event_chain_is_split_at_editorial_maximum():
    events = [{"start": time, "end": time + 1, "type": "combat"} for time in (0, 4, 8, 12)]
    assert [len(group) for group in group_events(events, 5, max_span=10)] == [3, 1]


def test_ranking():
    assert score_event({"type":"combat","confidence":.8,"signals":{"motion":.5,"audio":.5}}, {"combat":4,"motion":2,"audio":2,"confidence":1}) == 6.0


def test_source_signature_is_stable_and_changes(tmp_path):
    source = tmp_path / "source.bin"; source.write_bytes(b"first")
    before = source_signature(source)
    assert before == source_signature(source)
    source.write_bytes(b"changed")
    assert before != source_signature(source)


def test_changed_source_invalidates_cached_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(project_module, "PROJECTS", tmp_path / "projects")
    source = tmp_path / "video.mp4"; source.write_bytes(b"first")
    folder = project_module.create_project(source, {"path": str(source)}, {})
    (folder / "transcript.json").write_text("{}", encoding="utf-8")
    source.write_bytes(b"second version")
    project_module.create_project(source, {"path": str(source)}, {})
    assert not (folder / "transcript.json").exists()


def test_recent_projects_are_ordered_and_resumable(tmp_path, monkeypatch):
    monkeypatch.setattr(project_module, "PROJECTS", tmp_path / "projects")
    for name, updated in (("old", "2020-01-01"), ("new", "2021-01-01")):
        folder = project_module.PROJECTS / name; folder.mkdir(parents=True)
        (folder / "source.json").write_text('{"name":"' + name + '"}', encoding="utf-8")
        (folder / "project.json").write_text('{"updated_at":"' + updated + '"}', encoding="utf-8")
    assert [item["name"] for item in recent_projects()] == ["new", "old"]


def test_sfx_catalog_is_local_and_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(assets_module, "SFX_DIRECTORY", tmp_path)
    (tmp_path / "hit.wav").write_bytes(b"sound")
    (tmp_path / "notes.txt").write_text("no", encoding="utf-8")
    assert assets_module.list_sfx() == ["hit.wav"]
    assert assets_module.sfx_path("hit.wav").name == "hit.wav"
    try: assets_module.sfx_path("../notes.txt")
    except ValueError: pass
    else: raise AssertionError("Caminho externo de SFX deve falhar")


def test_project_log_is_human_readable(tmp_path):
    append_log(tmp_path, "Analisando vídeo")
    assert "Analisando vídeo" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_edl_duration_and_selection():
    highlights = [{"id":"a","start":1,"end":3,"reason":"combat","score":4,"selected":True}, {"id":"b","start":5,"end":9,"reason":"kill","score":8,"selected":False}]
    edl = make_edl("x.mp4", highlights, "60/1")
    assert edl_duration(edl["segments"]) == 2
    assert edl["fps_rational"] == "60/1"


def test_expected_render_duration_accounts_for_timed_effects():
    edl = {"segments": [{"start": 0, "end": 4, "effects": [{"type": "slow_motion"}]}, {"start": 10, "end": 12, "effects": [{"type": "freeze_frame"}]}]}
    assert expected_edl_duration(edl) == 8.5
    high = {"segments": [{"start": 0, "end": 4, "effects": [{"type": "slow_motion", "intensity": "high"}]}]}
    assert expected_edl_duration(high) == 8


def test_edl_uses_score_budget_but_keeps_source_order():
    highlights = [{"id":"late","start":30,"end":35,"reason":"combat","score":10,"selected":True}, {"id":"early","start":2,"end":7,"reason":"combat","score":9,"selected":True}, {"id":"middle","start":15,"end":20,"reason":"combat","score":1,"selected":True}]
    edl = make_edl("x.mp4", highlights, "60/1", target_duration=10)
    assert [segment["highlight_id"] for segment in edl["segments"]] == ["early", "late"]


def test_edl_fills_remaining_budget_with_next_best_highlight():
    highlights = [{"id":"best","start":20,"end":28,"reason":"combat","score":10,"selected":True}, {"id":"second","start":0,"end":8,"reason":"reaction","score":9,"selected":True}, {"id":"filler","start":10,"end":12,"reason":"conversation","score":1,"selected":True}]
    edl = make_edl("x.mp4", highlights, "60/1", target_duration=12)
    assert {segment["highlight_id"] for segment in edl["segments"]} == {"best", "second"}
    assert edl_duration(edl["segments"]) == 12


def test_short_source_uses_proportional_target_and_clips_single_long_segment():
    settings = {"short_video_max_seconds": 120, "short_video_target_ratio": .6, "short_video_min_target_seconds": 2}
    target = automatic_target_duration(10, settings)
    edl = make_edl("x.mp4", [{"id":"long","start":0,"end":10,"reason":"combat","score":9,"selected":True}], "60/1", target_duration=target)
    assert target == 6 and edl_duration(edl["segments"]) == 6


def test_long_source_uses_configured_automatic_edit_ratio_and_limits():
    settings = {"long_video_target_ratio": .35, "long_video_min_target_seconds": 180, "long_video_max_target_seconds": 600}
    assert automatic_target_duration(1308, settings) == 457.8
    assert automatic_target_duration(120, settings) == 180
    assert automatic_target_duration(3600, settings) == 600


def test_selected_highlights_must_be_inside_source_duration():
    validate_highlights([{"id":"ok","start":0,"end":3,"selected":True}], 3)
    try: validate_highlights([{"id":"bad","start":3,"end":2,"selected":True}], 4)
    except ValueError: pass
    else: raise AssertionError("Intervalo invertido precisa falhar")


def test_caption_style_moves_from_blocked_bottom_band():
    layout = {"regions": {"webcam": {"x": 0, "y": .7, "width": .3, "height": .3}, "hp": {"x": .4, "y": .75, "width": .2, "height": .2}}}
    assert not subtitle_style(layout, (1920, 1080)).startswith("Alignment=2")
    assert subtitle_style({"regions": {}}, (1920, 1080)).startswith("Alignment=2")


def test_ffmpeg_command_preserves_fps(tmp_path):
    command = segment_command(tmp_path / "in.mp4", {"start":0,"end":4}, tmp_path / "out.mp4", "60000/1001")
    assert "fps=60000/1001" in command
    assert "libx264" in command
    amf = segment_command(tmp_path / "in.mp4", {"start":0,"end":4}, tmp_path / "out.mp4", "60/1", video_encoder="h264_amf")
    assert "h264_amf" in amf
    limited = segment_command(tmp_path / "in.mp4", {"start":0,"end":4}, tmp_path / "out.mp4", "60/1", video_encoder="libx264", cpu_threads=4)
    thread_option = limited.index("-threads")
    assert limited[thread_option:thread_option + 2] == ["-threads", "4"]


def test_vertical_output_profile_builds_full_and_top_split_filters(tmp_path):
    full = normalize_output_settings({"output_format": "9:16", "vertical_mode": "full"})
    full_command = segment_command(tmp_path / "in.mp4", {"start": 0, "end": 4}, tmp_path / "full.mp4", "60/1", output_profile=full)
    assert "-filter_complex" in full_command and "scale=1080:1920" in full_command[full_command.index("-filter_complex") + 1]
    split = normalize_output_settings({"output_format": "9:16", "vertical_mode": "top_split"})
    split_command = segment_command(tmp_path / "in.mp4", {"start": 0, "end": 4}, tmp_path / "split.mp4", "60/1", output_profile=split)
    graph = split_command[split_command.index("-filter_complex") + 1]
    assert "scale=1080:608" in graph and "scale=1080:1312" in graph and "vstack=inputs=2" in graph
    assert output_size({"width": 1920, "height": 1080}, split) == (1080, 1920)


def test_top_split_webcam_crop_is_16_by_9_in_source_pixels():
    profile = fit_output_crops({"output_format": "9:16", "vertical_mode": "top_split"}, {"width": 1920, "height": 1080})
    webcam = profile["crops"]["webcam"]
    physical_aspect = webcam["width"] * 1920 / (webcam["height"] * 1080)
    assert abs(physical_aspect - 16 / 9) < .0001


def test_manual_captions_round_trip(tmp_path):
    output = tmp_path / "manual.srt"
    assert write_manual_srt([{"start": .5, "end": 1.8, "text": "Boa\njogada!"}], output) == 1
    assert read_srt_entries(output) == [{"start": .5, "end": 1.8, "text": "Boa\njogada!"}]


def test_update_version_comparison_ignores_v_prefix_and_prerelease():
    assert _version("v0.2.1") == (0, 2, 1)
    assert _version("1.3.4-beta") == (1, 3, 4)


def test_hardware_encoder_options_are_h264_amf_specific():
    assert encoder_options("h264_amf", 4) == ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22", "-threads", "4"]


def test_layout_requires_normalized_regions():
    layout = validate_layout({"regions": {"webcam": {"x": 0, "y": .7, "width": .25, "height": .3}}})
    assert layout["regions"]["webcam"]["height"] == .3
    try:
        validate_layout({"regions": {"webcam": {"x": .9, "y": 0, "width": .2, "height": .2}}})
    except ValueError:
        pass
    else:
        raise AssertionError("Layout fora do frame deveria falhar")


def test_job_status_is_serializable():
    manager = JobManager()
    job = manager.start("project", "test", lambda current: {"ok": True})
    snapshot = job.snapshot()
    assert snapshot["id"] == job.id and "cancelled" not in snapshot


def test_local_health_endpoint_identifies_this_application():
    assert health()["app"] == "Aizen Auto Editor"
    assert health()["status"] == "ok" and health()["version"] == "0.2.1"


def test_transcript_events_detect_reaction_and_pause():
    events = transcript_events({"segments": [{"start": 0, "end": 1, "text": "nossa, kkk!"}, {"start": 3, "end": 4, "text": "esse noob perdeu"}]})
    assert [event["type"] for event in events] == ["reaction", "idle", "trash_talk"]


def test_transcript_events_promote_free_fire_callouts_and_reduce_filler():
    events = transcript_events({"segments": [{"start": 0, "end": 1, "text": "Tá ali, tá ali"}, {"start": 1, "end": 2, "text": "entendi"}]})
    assert events[0]["type"] == "reaction" and events[0]["signals"]["speech_interest"] >= .8
    assert events[1]["type"] == "conversation" and events[1]["confidence"] < .2


def test_transcript_events_promote_spoken_kills_and_deaths():
    events = transcript_events({"segments": [{"start": 0, "end": 1, "text": "matei, dei capa"}, {"start": 2, "end": 3, "text": "morri, ele me matou"}]})
    assert [event["type"] for event in events if event["type"] != "idle"] == ["kill_candidate", "death_candidate"]


def test_transcription_reports_source_timeline_progress_without_loading_model():
    class Segment:
        def __init__(self, start, end): self.start, self.end, self.text, self.words = start, end, "fala", []
    class Info: language = "pt"
    class Model:
        def transcribe(self, *_args, **_kwargs): return iter([Segment(0, 2), Segment(2, 8)]), Info()
    transcriber = object.__new__(FasterWhisperTranscriber); transcriber.model = Model()
    updates = []
    result = transcriber.transcribe(Path("video.mp4"), duration=10, progress=updates.append)
    assert result["language"] == "pt" and updates == [.2, .8]


def test_adaptive_combat_threshold_finds_relative_action_burst():
    visual = [{"time": time, "motion": .02} for time in range(9)] + [{"time": 9, "motion": .4}]
    audio = [{"time": time, "energy": .04} for time in range(9)] + [{"time": 9, "energy": .5}]
    assert [event["start"] for event in detect_events(visual, audio, .55) if event["type"] == "combat_peak"] == [9]
    assert not [event for event in detect_events(visual[:-1], audio[:-1], .55) if event["type"] in {"combat", "combat_peak"}]


def test_free_fire_round_result_panel_is_detected_by_color_band():
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    y1, y2, x1, x2 = int(.29 * 90), int(.44 * 90), int(.15 * 160), int(.85 * 160)
    middle = (x1 + x2) // 2
    frame[y1:y2, x1:middle] = (255, 0, 0)
    frame[y1:y2, middle:x2] = (0, 90, 255)
    assert _round_result_score(frame) > .95
    gameplay = np.full_like(frame, (40, 110, 190))
    assert _round_result_score(gameplay) == 0


def test_captions_use_output_timeline_offsets(tmp_path):
    output = tmp_path / "captions.srt"
    count = build_srt({"segments": [{"start": 11, "end": 12, "text": "nossa!"}]}, [{"start": 10, "end": 15}, {"start": 20, "end": 25}], output, "all")
    assert count == 1 and "00:00:01,000 --> 00:00:02,000" in output.read_text(encoding="utf-8")
    assert srt_timestamp(3661.234) == "01:01:01,234"


def test_important_captions_cover_all_selected_speech_in_short_chunks(tmp_path):
    output = tmp_path / "captions.srt"
    phrase = {"start": 0, "end": 4, "text": "vamos subir naquela casa porque o inimigo está chegando agora"}
    count = build_srt({"segments": [phrase]}, [{"start": 0, "end": 4}], output, "Apenas momentos importantes")
    blocks = output.read_text(encoding="utf-8").strip().split("\n\n")
    assert count >= 2 and len(blocks) == count
    assert all(len(" ".join(block.splitlines()[2:]).split()) <= 5 for block in blocks)
    assert _caption_chunks({"start": 0, "end": 4, "text": "vai"}, 0, 4)[0][1] == 2.4
    assert _caption_chunks({"start": 0, "end": 1, "text": "palavramuitolongasemespaco"}, 0, 1)[0][2] == "palavramuitolongasemespaco"


def test_empty_caption_selection_removes_stale_subtitle_file(tmp_path):
    output = tmp_path / "captions.srt"; output.write_text("old", encoding="utf-8")
    assert build_srt({"segments": []}, [{"start": 0, "end": 1}], output, "all") == 0
    assert not output.exists()


def test_activity_score_combines_motion_audio_and_speech():
    score = build_activity_score([{"time": 1, "motion": .8}], [{"time": 1, "energy": .5}], {"segments": [{"start": .5, "end": 1.5}]})
    assert score == [{"time": 1, "activity": .75, "motion": .8, "audio": .5, "speech": 1.0}]


def test_dead_zone_requires_sustained_multi_signal_inactivity():
    settings = {"minimum_seconds": 2, "max_activity": .2, "max_motion": .16, "max_audio": .18, "max_hud": .12}
    quiet = [{"time": time, "activity": .04, "motion": .02, "audio": .1, "speech": 0.0} for time in (0, 1, 2)]
    assert detect_dead_zones(quiet, settings)[0]["end"] == 3
    quiet[1]["motion"] = .8
    assert not detect_dead_zones(quiet, settings)


def test_effects_are_validated_and_generate_filters():
    effect = validate_effect({"type": "slow_motion", "start": 0, "end": 2})
    video, audio = filters_for_effects([effect])
    assert "setpts=1.5*PTS" in video and "atempo=0.666667" in audio
    graph = windowed_video_filtergraph([{"type": "punch_zoom", "start": 0, "end": 1}], None, "60/1", 720)
    assert "overlay=0:0:enable='between(t,0,1)'" in graph and "scale=-2:720" in graph
    assert "iw/1.18" in windowed_video_filtergraph([{"type": "punch_zoom", "start": 0, "end": 1, "intensity": "high"}], None, "60/1", None)


def test_config_can_disable_an_effect():
    try: validate_effect({"type": "text", "start": 0, "end": 1, "text": "oi"}, {"text": False})
    except ValueError: pass
    else: raise AssertionError("Efeito desativado precisa ser recusado")


def test_webcam_effect_requires_calibration():
    effect = {"type": "webcam_punch_in", "start": 0, "end": 1}
    try: filters_for_effects([effect])
    except ValueError: pass
    else: raise AssertionError("Webcam punch-in exige área calibrada")


def test_local_llm_is_off_without_model():
    llm = LocalLLM()
    assert not llm.enabled and not llm.available() and llm.classify_excerpt("teste") is None


def test_audio_timeline_uses_requested_step():
    assert list(_times(2.1, 1.0)) == [0.0, 1.0, 2.0]


def test_nonfinite_audio_and_legacy_activity_are_repaired():
    assert not audio_features_are_finite([{"time": 0, "energy": float("nan")}])
    repaired = sanitize_activity([{"time": 0, "activity": float("nan"), "audio": float("inf"), "motion": .2, "speech": 0}])
    assert repaired == [{"time": 0, "activity": 0.0, "audio": 0.0, "motion": .2, "speech": 0}]


def test_highlights_are_clamped_to_source_duration():
    highlights = build_highlights([{"start": 2, "end": 3, "type": "combat", "confidence": 1, "signals": {"motion": 1, "audio": 1}}], {"combat": 4, "motion": 2, "audio": 2, "confidence": 1}, {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 5, "minimum_score": 0}, 4.416)
    assert highlights[0]["start"] == 0 and highlights[0]["end"] == 4.416


def test_short_video_highlights_use_shorter_context():
    settings = {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 5, "minimum_score": 0, "short_video_max_seconds": 120, "short_video_context_ratio": .1}
    event = {"start": 5, "end": 6, "type": "combat", "confidence": 1, "signals": {"motion": 1, "audio": 1}}
    highlight = build_highlights([event], {"combat": 4, "motion": 2, "audio": 2, "confidence": 1}, settings, 10)[0]
    assert highlight["start"] == 4 and highlight["end"] == 7


def test_round_end_keeps_extra_context_before_kill_or_death():
    settings = {"pre_context_seconds": 3, "post_context_seconds": 3, "round_end_pre_context_seconds": 5, "merge_gap_seconds": 4, "minimum_score": 0}
    event = {"start": 10, "end": 11, "type": "round_end", "confidence": 1, "signals": {}}
    highlight = build_highlights([event], {"round_end": 9}, settings, 20)[0]
    assert highlight["start"] == 5 and highlight["end"] == 14


def test_dead_zones_trim_highlight_context():
    settings = {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 5, "minimum_score": 0}
    event = {"start": 10, "end": 11, "type": "combat", "confidence": 1, "signals": {"motion": 1, "audio": 1}}
    zones = [{"start": 7, "end": 9, "type": "dead_zone"}, {"start": 12, "end": 14, "type": "dead_zone"}]
    highlight = build_highlights([event], {"combat": 4, "motion": 2, "audio": 2, "confidence": 1}, settings, 20, zones)[0]
    assert highlight["start"] == 9 and highlight["end"] == 12


def test_repeated_generic_conversation_does_not_inflate_highlight_score():
    settings = {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 5, "minimum_score": 2, "max_conversation_events": 3}
    events = [{"start": time, "end": time + .5, "type": "conversation", "confidence": .18, "signals": {"speech": 1}} for time in range(10)]
    weights = {"conversation": 1.5, "confidence": 1}
    assert build_highlights(events, weights, settings, 20) == []


def test_adjacent_highlight_context_is_not_rendered_twice():
    settings = {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 1, "minimum_score": 0}
    events = [{"start": 5, "end": 6, "type": "combat", "confidence": 1, "signals": {}}, {"start": 8, "end": 9, "type": "combat", "confidence": 1, "signals": {}}]
    highlights = sorted(build_highlights(events, {"combat": 4}, settings, 15), key=lambda item: item["start"])
    assert highlights[0]["end"] == highlights[1]["start"]


def test_edit_type_changes_highlight_context_and_threshold():
    base = {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 5, "minimum_score": 2}
    dynamic = style_highlight_settings(base, "Mais dinâmica")
    natural = style_highlight_settings(base, "Mais natural")
    best = style_highlight_settings(base, "Só melhores momentos")
    assert dynamic["pre_context_seconds"] < base["pre_context_seconds"]
    assert natural["merge_gap_seconds"] > base["merge_gap_seconds"]
    assert best["minimum_score"] > base["minimum_score"]


def test_outcome_candidates_require_hud_and_combat_signals():
    combat = {"start": 4, "end": 5, "type": "combat", "confidence": .9, "signals": {"motion": .7, "audio": .6, "kill_feed": .7, "hp": 0}}
    result = detect_outcome_candidates([combat])
    assert result[0]["type"] == "kill_candidate"
    assert not detect_outcome_candidates([{**combat, "signals": {"motion": .7, "audio": .6, "kill_feed": 0, "hp": 0}}])
