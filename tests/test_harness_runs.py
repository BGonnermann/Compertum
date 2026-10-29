import pytest

from compertum.harness.runs import MEMORY_FLOOR, RunError, RunManager

TESTS = ["tests/test_harness_example.py"]


class Process:
    pid = 1234
    def __init__(self):
        self.code = None
        self.terminated = False
    def poll(self):
        return self.code
    def terminate(self):
        self.terminated = True
        self.code = 1


def test_owner_started_test_run_has_a_uniform_card_and_stops(tmp_path):
    processes = []
    commands = []
    def spawn(command, **kwargs):
        commands.append(command)
        process = Process()
        processes.append(process)
        kwargs["stdout"].write(b"tests/example.py ..... [100%]\n===== 1 passed in 0.1s =====\n")
        return process
    manager = RunManager(tmp_path, spawn=spawn, available_memory=lambda: MEMORY_FLOOR)
    with pytest.raises(RunError, match="no harness test files"):
        manager.start("test")
    (tmp_path / "tests").mkdir()
    for name in ("test_harness_b.py", "test_harness_a.py", "test_other.py"):
        (tmp_path / "tests" / name).write_text("")
    card = manager.start("test")
    assert commands[0][3:5] == ["tests/test_harness_a.py", "tests/test_harness_b.py"]
    assert card["type"] == "test"
    assert card["status"] == "RUNNING"
    assert card["progress"] == "100%"
    assert "1 passed" in card["result"]
    assert manager.stop(card["run"])["status"] == "FAILED"
    assert processes[0].terminated
    second = manager.start("gepa", cycles=2, requests=100, hours=1, note="fake owner run")
    assert second["status"] == "RUNNING"
    assert "-Mode" in commands[1] and "gepa" in commands[1]
    assert "-Cycles" in commands[1] and "2" in commands[1]
    processes[-1].code = 0
    third = manager.start("bench", cycles=3, requests=100, hours=1, note="fake owner bench")
    assert third["status"] == "RUNNING"
    assert "-Cycles" not in commands[2]
    assert "-CyclesPerMarket" in commands[2] and "3" in commands[2]


def test_run_recovers_the_original_process_after_a_console_restart(tmp_path):
    process = Process()
    manager = RunManager(tmp_path, spawn=lambda *a, **k: process, available_memory=lambda: MEMORY_FLOOR)
    card = manager.start("test", paths=TESTS)
    recovered = RunManager(tmp_path, available_memory=lambda: MEMORY_FLOOR, adopt=lambda meta: process)
    assert recovered.card(card["run"])["recovered"] is True
    assert recovered.card(card["run"])["status"] == "RUNNING"
    assert recovered.stop(card["run"])["status"] == "FAILED"
    finished = RunManager(tmp_path, available_memory=lambda: MEMORY_FLOOR,
                          adopt=lambda meta: pytest.fail("a finished process needs no operating-system handle"))
    assert finished.card(card["run"])["exit_code"] == 1


def test_run_refuses_low_memory_and_a_second_active_job(tmp_path):
    manager = RunManager(tmp_path, spawn=lambda *a, **k: Process(), available_memory=lambda: MEMORY_FLOOR - 1)
    with pytest.raises(RunError, match="AVAILABLE_RAM_FLOOR"):
        manager.start("test", paths=TESTS)
    manager.available_memory = lambda: MEMORY_FLOOR
    manager.start("test", paths=TESTS)
    with pytest.raises(RunError, match="active"):
        manager.start("test", paths=TESTS)


def test_finished_engine_stop_does_not_plant_the_kill_switch(tmp_path):
    process = Process()
    manager = RunManager(tmp_path, spawn=lambda *a, **k: process, available_memory=lambda: MEMORY_FLOOR)
    card = manager.start("gepa", cycles=1, requests=10, hours=1, note="fake")
    process.code = 0
    assert manager.stop(card["run"])["status"] == "COMPLETED"
    assert not (tmp_path / "state" / "engine" / "STOP").exists()


def test_engine_expiry_uses_the_kill_switch_not_wrapper_termination(tmp_path):
    process = Process()
    manager = RunManager(tmp_path, spawn=lambda *a, **k: process, available_memory=lambda: MEMORY_FLOOR)
    card = manager.start("practice", cycles=1, requests=10, hours=1, note="fake")
    manager._expire(card["run"])
    assert (tmp_path / "state" / "engine" / "STOP").is_file()
    assert not process.terminated


def test_lost_run_does_not_block_and_absolute_test_path_is_refused(tmp_path):
    lost = Process()
    lost.code = "LOST"
    manager = RunManager(tmp_path, spawn=lambda *a, **k: Process(), available_memory=lambda: MEMORY_FLOOR)
    manager.active["lost"] = {"process": lost}
    with pytest.raises(RunError, match="inside"):
        manager.start("test", paths=[str(tmp_path.parent / "outside.py")])


def test_owner_can_dismiss_an_unverifiable_terminal_record(tmp_path):
    manager = RunManager(tmp_path, spawn=lambda *a, **k: Process(), available_memory=lambda: MEMORY_FLOOR)
    card = manager.start("test", paths=TESTS)
    manager.active[card["run"]]["process"].code = "UNKNOWN"
    with pytest.raises(RunError, match="unverified"):
        manager.start("test", paths=TESTS)
    assert manager.clear(card["run"])["status"] == "DISMISSED"
    assert manager.start("test", paths=TESTS)["status"] == "RUNNING"


def test_engine_stop_clears_only_its_own_kill_switch_and_cards_stay_true(tmp_path):
    processes, options = [], []

    def spawn(command, **kwargs):
        options.append(kwargs)
        processes.append(Process())
        return processes[-1]

    manager = RunManager(tmp_path, spawn=spawn, available_memory=lambda: MEMORY_FLOOR)
    first = manager.start("gepa", cycles=1, requests=10, hours=1, note="first")["run"]
    assert options[0]["stdin"] is __import__("subprocess").DEVNULL
    manager.stop(first)
    stop = tmp_path / "state" / "engine" / "STOP"
    assert stop.exists()
    processes[0].code = 1
    assert manager.card(first)["status"] == "FAILED"
    assert not stop.exists()  # The harness set it, and the run has ended, so the next run may start.
    second = manager.start("gepa", cycles=1, requests=10, hours=1, note="second")["run"]
    stop.touch()  # The owner's own kill switch.
    processes[1].code = 0
    manager.card(second)
    assert stop.exists()
    with pytest.raises(RunError, match="state/engine/STOP exists"):
        manager.start("bench", cycles=1, requests=10, hours=1, note="blocked")
    assert manager.latest() == second
    manager.clear(second)
    assert manager.latest() == first
    log = tmp_path / "state" / "harness" / "runs" / f"{first}.log"
    import os
    import time
    record = manager.active[first]
    os.utime(log, (record["started_wall"] + 30, record["started_wall"] + 30))
    assert manager.card(first)["elapsed_seconds"] == 30.0  # A finished run's time stops at its last log write.
