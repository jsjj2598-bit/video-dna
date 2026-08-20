from app.services.tasks import TaskStore


def test_task_store_does_not_keep_analysis_result():
    store = TaskStore()
    store.create("session", "uploaded")
    store.report("session", "shots", 20, "four shots")
    store.finish("session")

    state = store.get("session")

    assert state["stage"] == "done"
    assert state["done"] is True
    assert "result" not in state

