/** PCM16 capture/playback helpers ported from legacy frontend/index.html */

export function resample(buffer: Float32Array, fromRate: number, toRate: number): Float32Array | null {
  if (fromRate === toRate) return buffer;
  if (toRate > fromRate) return null;
  const ratio = fromRate / toRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const idx = i * ratio;
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, buffer.length - 1);
    const frac = idx - lo;
    result[i] = buffer[lo] * (1 - frac) + buffer[hi] * frac;
  }
  return result;
}

export function convertToPCM16(float32Array: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32Array.length; i++) {
    const sample = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

export function pcm16ToFloat32(arrayBuffer: ArrayBuffer): Float32Array {
  const int16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;
  return float32;
}

export function computeEnergy(buffer: Float32Array): number {
  if (!buffer.length) return 0;
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
  return Math.sqrt(sum / buffer.length);
}

export function mergeFloat32(chunks: Float32Array[]): Float32Array {
  if (chunks.length === 0) return new Float32Array(0);
  if (chunks.length === 1) return chunks[0]!;
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}
