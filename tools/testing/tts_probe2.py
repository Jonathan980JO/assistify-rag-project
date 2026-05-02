import asyncio, time, aiohttp

URL = 'http://127.0.0.1:7000/tts'
TEXTS = [
    'Psychology is the scientific study of mind and behavior.',
    'Psychology is the scientific study of mind and behavior.',
    'The goals of psychology are description, explanation, prediction, and control of behavior.',
    'In psychology, control of behavior means using research findings to influence or change behavior, for example to help people overcome anxiety.',
]


async def hit(text, idx):
    print('\n=== /tts probe %d text_len=%d ===' % (idx, len(text)))
    t0 = time.perf_counter()
    print('[TTS PLAYBACK probe] request started t=0ms')
    async with aiohttp.ClientSession() as s:
        async with s.post(
            URL,
            json={'text': text},
            timeout=aiohttp.ClientTimeout(total=180, sock_connect=5, sock_read=None),
        ) as r:
            t_h = time.perf_counter()
            xc = r.headers.get('X-Chunks', '?')
            xid = r.headers.get('X-TTS-Req-Id', '?')
            print('[TTS PLAYBACK probe] headers status=%d t=%dms x_chunks=%s x_id=%s'
                  % (r.status, int((t_h - t0) * 1000), xc, xid))
            if r.status != 200:
                print('FAIL', await r.text())
                return
            first = None
            total = 0
            n = 0
            async for chunk in r.content.iter_chunked(4096):
                if first is None:
                    first = time.perf_counter()
                    print('[TTS PLAYBACK probe] first audio chunk t=%dms bytes=%d'
                          % (int((first - t0) * 1000), len(chunk)))
                total += len(chunk)
                n += 1
            t_e = time.perf_counter()
            print('[TTS PLAYBACK probe] audio finished t=%dms bytes=%d chunks=%d'
                  % (int((t_e - t0) * 1000), total, n))


async def main():
    for i, t in enumerate(TEXTS, 1):
        try:
            await hit(t, i)
        except Exception as e:
            print('ERR', e)
        await asyncio.sleep(0.3)


asyncio.run(main())
