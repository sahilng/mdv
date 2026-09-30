"""Measure editing refreshes: .venv/bin/python scripts/benchmark_editing.py."""

import argparse
import asyncio
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from mdv.app import Viewer
from mdv.editor import MarkdownEditor
from mdv.rendered import RenderMarkdown, aligned_snapshot, styled_source


async def benchmark(path, live, iterations):
    app = Viewer(path, start_editing=True, live_edit=live)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.2)
        await app.workers.wait_for_complete()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        # Isolate refresh work from timers and status updates. The event loop
        # continues serving native TextArea editing and DOM mount operations.
        app.schedule_scroll_sync = lambda: None
        app.on_text_area_changed = lambda event: None
        if app._typing_timer is not None:
            app._typing_timer.stop()
        editor = app.query_one(MarkdownEditor)
        renderer = app.query_one(RenderMarkdown)
        editing, rendering, projecting = [], [], []
        for _ in range(iterations):
            start = perf_counter()
            editor.insert('x', location=(2, 0))
            editing.append(perf_counter() - start)
            start = perf_counter()
            await renderer.update(editor.text)
            for block in renderer.query('MarkdownFence'):
                content = getattr(block, '_mdv_content', None)
                if content is not None:
                    block.set_content(content)
            rendering.append(perf_counter() - start)
            start = perf_counter()
            if live:
                editor.set_styles(styled_source(renderer, editor.document.lines), renderer)
            else:
                aligned_snapshot(renderer, editor)
            projecting.append(perf_counter() - start)
            await pilot.pause()
        mode = 'live' if live else 'split'
        print(f'{mode:5s}: edit {median(editing) * 1000:7.2f} ms, '
              f'render {median(rendering) * 1000:7.2f} ms, '
              f'projection {median(projecting) * 1000:7.2f} ms')


async def main(paragraphs, iterations):
    with TemporaryDirectory(prefix='mdv-benchmark-') as directory:
        path = Path(directory) / 'document.md'
        path.write_text('# Heading\n\nFirst paragraph\n\n' + '\n\n'.join(
            f'Paragraph {index}: **bold** and *italic*, '
            f'[link](https://example.com/{index}) and `code`.'
            for index in range(paragraphs)) + '\n', encoding='utf-8')
        print(f'{paragraphs} paragraphs; median of {iterations} single-character edits')
        for live in (False, True):
            await benchmark(path, live, iterations)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paragraphs', type=int, default=300)
    parser.add_argument('--iterations', type=int, default=7)
    args = parser.parse_args()
    asyncio.run(main(args.paragraphs, args.iterations))
