from app.core.edl import edl_duration, make_edl
from app.core.gameplay import normalized_to_pixels
from app.core.highlights import group_events
from app.core.layout import validate_layout
from app.core.jobs import JobManager
from app.core.project import source_signature
from app.core import project as project_module
from app.core.probe import _ratio
from app.core.ranking import score_event
from app.core.renderer import segment_command
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


def test_edl_duration_and_selection():
    highlights = [{"id":"a","start":1,"end":3,"reason":"combat","score":4,"selected":True}, {"id":"b","start":5,"end":9,"reason":"kill","score":8,"selected":False}]
    edl = make_edl("x.mp4", highlights, "60/1")
    assert edl_duration(edl["segments"]) == 2
    assert edl["fps_rational"] == "60/1"


def test_ffmpeg_command_preserves_fps(tmp_path):
    command = segment_command(tmp_path / "in.mp4", {"start":0,"end":4}, tmp_path / "out.mp4", "60000/1001")
    assert "fps=60000/1001" in command


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
