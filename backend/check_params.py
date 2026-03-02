from pipecat.pipeline.task import PipelineParams
import inspect

print("PipelineParams signature:")
print(inspect.signature(PipelineParams))

print("\nPipelineParams fields:")
for field in PipelineParams.__dataclass_fields__:
    f = PipelineParams.__dataclass_fields__[field]
    print(f"  {field}: {f.type} = {f.default}")
