from pipecat.frames.frames import FunctionCallInProgressFrame
print("FunctionCallInProgressFrame:", FunctionCallInProgressFrame)

# Check if FunctionCallsStartedFrame exists
try:
    from pipecat.frames.frames import FunctionCallsStartedFrame
    print("FunctionCallsStartedFrame:", FunctionCallsStartedFrame)
except ImportError:
    print("FunctionCallsStartedFrame: Not found in pipecat.frames.frames")

# Check aggregators
try:
    from pipecat.processors.aggregators.llm_response import FunctionCallsStartedFrame as FCStart
    print("FunctionCallsStartedFrame from aggregators:", FCStart)
except ImportError:
    print("Not in aggregators either")
