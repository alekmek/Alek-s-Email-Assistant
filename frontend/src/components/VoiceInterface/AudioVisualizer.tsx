interface AudioVisualizerProps {
  level: number; // 0-1
  isActive: boolean;
}

export function AudioVisualizer({ level, isActive }: AudioVisualizerProps) {
  // Generate bar heights based on audio level
  const barCount = 5;
  const bars = Array.from({ length: barCount }, (_, i) => {
    const baseHeight = 8;
    const maxAdditional = 40;

    // Create a wave-like pattern
    const offset = i - Math.floor(barCount / 2);
    const normalizedOffset = 1 - Math.abs(offset) / (barCount / 2);

    const height = isActive
      ? baseHeight + maxAdditional * level * normalizedOffset * (0.5 + Math.random() * 0.5)
      : baseHeight;

    return Math.max(baseHeight, Math.min(baseHeight + maxAdditional, height));
  });

  return (
    <div className="flex items-center justify-center gap-1 h-16">
      {bars.map((height, i) => (
        <div
          key={i}
          className={`w-2 rounded-full transition-all duration-75 ${
            isActive ? 'bg-indigo-500' : 'bg-slate-600'
          }`}
          style={{
            height: `${height}px`,
          }}
        />
      ))}
    </div>
  );
}
