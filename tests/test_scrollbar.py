import pytest

from mdv.scrollbar import SolidScrollBarRender


@pytest.mark.parametrize("vertical", [False, True])
@pytest.mark.parametrize("window,virtual,position", [
    (5, 100, -20), (5, 100, 10_000), (100, 5, 30), (0, 0, 30),
])
def test_scrollbar_resize_measurements_never_paint_outside_track(vertical, window, virtual, position):
    rendered = SolidScrollBarRender.render_bar(
        size=7, window_size=window, virtual_size=virtual,
        position=position, thickness=2 if vertical else 1, vertical=vertical,
    )
    cells = [segment for segment in rendered.segments if segment.text != "\n"]
    assert len(cells) == 7
    assert all(segment.text == ("  " if vertical else " ") for segment in cells)
    assert all(not segment.style.reverse for segment in cells)
    assert all(segment.style.bgcolor is not None for segment in cells)
