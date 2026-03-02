try:
    from pipecat.frames.frames import FunctionCallsFinishedFrame
    print("FunctionCallsFinishedFrame:", FunctionCallsFinishedFrame)
except ImportError:
    print("FunctionCallsFinishedFrame: Not found")

try:
    from pipecat.frames.frames import FunctionCallResultFrame
    print("FunctionCallResultFrame:", FunctionCallResultFrame)
except ImportError:
    print("FunctionCallResultFrame: Not found")
