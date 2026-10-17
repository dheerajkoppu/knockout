import { writeFileSync } from "node:fs";

// 32-bit IEEE float WAV, channels given as equal-length Float32Arrays.
export function writeFloatWav(filePath, channels, sampleRate) {
  const channelCount = channels.length;
  const frameCount = channels[0].length;
  const dataBytes = frameCount * channelCount * 4;
  const header = Buffer.alloc(58);
  header.write("RIFF", 0);
  header.writeUInt32LE(50 + dataBytes, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(18, 16);
  header.writeUInt16LE(3, 20);
  header.writeUInt16LE(channelCount, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * channelCount * 4, 28);
  header.writeUInt16LE(channelCount * 4, 32);
  header.writeUInt16LE(32, 34);
  header.writeUInt16LE(0, 36);
  header.write("fact", 38);
  header.writeUInt32LE(4, 42);
  header.writeUInt32LE(frameCount, 46);
  header.write("data", 50);
  header.writeUInt32LE(dataBytes, 54);
  const interleaved = new Float32Array(frameCount * channelCount);
  for (let channel = 0; channel < channelCount; channel++) {
    const samples = channels[channel];
    for (let frame = 0; frame < frameCount; frame++) {
      interleaved[frame * channelCount + channel] = samples[frame];
    }
  }
  writeFileSync(filePath, Buffer.concat([header, Buffer.from(interleaved.buffer)]));
}
