
from fakes import as_dict
from tool.list.hello_world import hello_world


def test_hello_world_returns_greeting_json():
    parsed = as_dict(hello_world.func(name="Mario"))
    assert parsed == {"response": "Hello, Mario!"}
