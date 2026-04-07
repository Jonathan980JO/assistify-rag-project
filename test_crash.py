import traceback
import sys
try:
    from backend.assistify_rag_server import app, LiveRAGManager
    lm = LiveRAGManager()
except Exception as e:
    with open('traceback.txt', 'w') as f:
        f.write(traceback.format_exc())
    print("Traceback saved")
