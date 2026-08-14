from app.core.edl import edl_duration, make_edl, validate_highlights
from app.core.effects import filters_for_effects, validate_effect, windowed_video_filtergraph
from app.core.captions import build_srt, srt_timestamp
from app.core.gameplay import normalized_to_pixels, detect_outcome_candidates, save_debug_frames
from app.core.gameplay import build_activity_score
from app.core.audio import _times
from app.core.highlights import group_events
from app.core.highlights import build_highlights
from app.core.layout import validate_layout
from app.core.local_llm import LocalLLM
from app.core.jobs import JobManager
from app.core.project import source_signature
from app.core.project import append_log
from app.core import project as project_module
from app.core.probe import _ratio
from app.core.ranking import score_event
from app.core.renderer import segment_command, subtitle_style
from app.core.speech import transcript_events


def test_fps_rational_parsing():
    assert abs(_ratio("60000/1001") - 59.94005994) < .0001


def test_normalized_coordinates():
    assert normalized_to_pixels({"x": .1, "y": .2, "width": .5, "height": .25}, 1920, 1080) == {"x": 192, "y": 216, "width": 960, "height": 270}


def test_group_events():
    events = [{"start": 10, "end": 11, "type": "combat"}, {"start": 14, "end": 15, "type": "kill"}, {"start": 30, "end": 31, "type": "combat"}]
    assert [len(x) for x in group_events(events, 5)] == [2, 1]


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


def test_project_log_is_human_readable(tmp_path):
    append_log(tmp_path, "Analisando vídeo")
    assert "Analisando vídeo" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_edl_duration_and_selection():
    highlights = [{"id":"a","start":1,"end":3,"reason":"combat","score":4,"selected":True}, {"id":"b","start":5,"end":9,"reason":"kill","score":8,"selected":False}]
    edl = make_edl("x.mp4", highlights, "60/1")
    assert edl_duration(edl["segments"]) == 2
    assert edl["fps_rational"] == "60/1"


def test_edl_uses_score_budget_but_keeps_source_order():
    highlights = [{"id":"late","start":30,"end":35,"reason":"combat","score":10,"selected":True}, {"id":"early","start":2,"end":7,"reason":"combat","score":9,"selected":True}, {"id":"middle","start":15,"end":20,"reason":"combat","score":1,"selected":True}]
    edl = make_edl("x.mp4", highlights, "60/1", target_duration=10)
    assert [segment["highlight_id"] for segment in edl["segments"]] == ["early", "late"]


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


def test_transcript_events_detect_reaction_and_pause():
    events = transcript_events({"segments": [{"start": 0, "end": 1, "text": "nossa, kkk!"}, {"start": 3, "end": 4, "text": "esse noob perdeu"}]})
    assert [event["type"] for event in events] == ["reaction", "idle", "trash_talk"]


def test_captions_use_output_timeline_offsets(tmp_path):
    output = tmp_path / "captions.srt"
    count = build_srt({"segments": [{"start": 11, "end": 12, "text": "nossa!"}]}, [{"start": 10, "end": 15}, {"start": 20, "end": 25}], output, "all")
    assert count == 1 and "00:00:01,000 --> 00:00:02,000" in output.read_text(encoding="utf-8")
    assert srt_timestamp(3661.234) == "01:01:01,234"


def test_activity_score_combines_motion_audio_and_speech():
    score = build_activity_score([{"time": 1, "motion": .8}], [{"time": 1, "energy": .5}], {"segments": [{"start": .5, "end": 1.5}]})
    assert score == [{"time": 1, "activity": .75, "motion": .8, "audio": .5, "speech": 1.0}]


def test_effects_are_validated_and_generate_filters():
    effect = validate_effect({"type": "slow_motion", "start": 0, "end": 2})
    video, audio = filters_for_effects([effect])
    assert "setpts=1.5*PTS" in video and "atempo=0.666667" in audio
    graph = windowed_video_filtergraph([{"type": "punch_zoom", "start": 0, "end": 1}], None, "60/1", 720)
    assert "overlay=0:0:enable='between(t,0,1)'" in graph and "scale=-2:720" in graph


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


def test_highlights_are_clamped_to_source_duration():
    highlights = build_highlights([{"start": 2, "end": 3, "type": "combat", "confidence": 1, "signals": {"motion": 1, "audio": 1}}], {"combat": 4, "motion": 2, "audio": 2, "confidence": 1}, {"pre_context_seconds": 3, "post_context_seconds": 3, "merge_gap_seconds": 5, "minimum_score": 0}, 4.416)
    assert highlights[0]["start"] == 0 and highlights[0]["end"] == 4.416


def test_outcome_candidates_require_hud_and_combat_signals():
    combat = {"start": 4, "end": 5, "type": "combat", "confidence": .9, "signals": {"motion": .7, "audio": .6, "kill_feed": .7, "hp": 0}}
    result = detect_outcome_candidates([combat])
    assert result[0]["type"] == "kill_candidate"
    assert not detect_outcome_candidates([{**combat, "signals": {"motion": .7, "audio": .6, "kill_feed": 0, "hp": 0}}])
