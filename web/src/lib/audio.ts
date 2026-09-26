"use client";

// Subtle, synthesized sound design (Web Audio, no samples):
//   hum    - a low, slowly breathing drone
//   riser  - a tone that climbs while a cluster is being acquired
//   lock   - a crisp click + two pings with a short echo
//   pulse  - a sub thump when the detection shockwave fires
//   launch - a filtered-noise whoosh when a swarm launches
//   flip   - a soft chord when governance flips to the honest result
class AudioEngine {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private fx: GainNode | null = null;
  private riserOsc: OscillatorNode | null = null;
  private riserGain: GainNode | null = null;
  enabled = false;

  private ensure() {
    if (this.ctx) return this.ctx;
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);
    // short feedback delay for a sense of space
    const fx = ctx.createGain();
    const delay = ctx.createDelay(1);
    delay.delayTime.value = 0.19;
    const fb = ctx.createGain();
    fb.gain.value = 0.28;
    const wet = ctx.createGain();
    wet.gain.value = 0.35;
    fx.connect(master);
    fx.connect(delay);
    delay.connect(fb);
    fb.connect(delay);
    delay.connect(wet);
    wet.connect(master);

    // hum: two detuned oscillators through a breathing low-pass
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 210;
    filter.Q.value = 0.8;
    const humGain = ctx.createGain();
    humGain.gain.value = 0.05;
    for (const [type, f] of [["sine", 55], ["sawtooth", 55.35], ["sine", 82.6]] as const) {
      const o = ctx.createOscillator();
      o.type = type;
      o.frequency.value = f;
      const g = ctx.createGain();
      g.gain.value = type === "sawtooth" ? 0.35 : 0.8;
      o.connect(g);
      g.connect(filter);
      o.start();
    }
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.07;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 70;
    lfo.connect(lfoGain);
    lfoGain.connect(filter.frequency);
    lfo.start();
    filter.connect(humGain);
    humGain.connect(master);

    // riser
    const riserOsc = ctx.createOscillator();
    riserOsc.type = "triangle";
    riserOsc.frequency.value = 180;
    const band = ctx.createBiquadFilter();
    band.type = "bandpass";
    band.frequency.value = 900;
    band.Q.value = 0.9;
    const riserGain = ctx.createGain();
    riserGain.gain.value = 0;
    riserOsc.connect(band);
    band.connect(riserGain);
    riserGain.connect(fx);
    riserOsc.start();

    this.ctx = ctx;
    this.master = master;
    this.fx = fx;
    this.riserOsc = riserOsc;
    this.riserGain = riserGain;
    return ctx;
  }

  async enable() {
    const ctx = this.ensure();
    await ctx.resume();
    this.enabled = true;
    this.master!.gain.setTargetAtTime(0.9, ctx.currentTime, 0.6);
  }

  disable() {
    if (!this.ctx || !this.master) return;
    this.enabled = false;
    this.master.gain.setTargetAtTime(0, this.ctx.currentTime, 0.25);
  }

  /** 0..1 while a cluster is being acquired; 0 once locked or gone. */
  tension(x: number) {
    if (!this.ctx || !this.riserOsc || !this.riserGain) return;
    const t = this.ctx.currentTime;
    this.riserOsc.frequency.setTargetAtTime(180 + x * 620, t, 0.4);
    this.riserGain.gain.setTargetAtTime(this.enabled ? x * 0.045 : 0, t, 0.3);
  }

  private noise(duration: number) {
    const ctx = this.ctx!;
    const buf = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * duration), ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    return src;
  }

  private ping(freq: number, at: number, gain: number, decay: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = "sine";
    o.frequency.value = freq;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(gain, at + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, at + decay);
    o.connect(g);
    g.connect(this.fx!);
    o.start(at);
    o.stop(at + decay + 0.05);
  }

  lock() {
    if (!this.enabled || !this.ctx) return;
    const ctx = this.ctx;
    const t = ctx.currentTime + 0.01;
    const click = this.noise(0.04);
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 2400;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.18, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.04);
    click.connect(hp);
    hp.connect(g);
    g.connect(this.fx!);
    click.start(t);
    this.ping(1318.5, t + 0.02, 0.09, 0.45);
    this.ping(1975.5, t + 0.1, 0.06, 0.6);
    this.tension(0);
  }

  pulse() {
    if (!this.enabled || !this.ctx) return;
    const ctx = this.ctx;
    const t = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = "sine";
    o.frequency.setValueAtTime(120, t);
    o.frequency.exponentialRampToValueAtTime(34, t + 0.9);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.28, t + 0.03);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 1.1);
    o.connect(g);
    g.connect(this.master!);
    o.start(t);
    o.stop(t + 1.2);
  }

  launch() {
    if (!this.enabled || !this.ctx) return;
    const ctx = this.ctx;
    const t = ctx.currentTime;
    const n = this.noise(1.6);
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.setValueAtTime(160, t);
    lp.frequency.exponentialRampToValueAtTime(1600, t + 1.3);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.09, t + 0.5);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 1.6);
    n.connect(lp);
    lp.connect(g);
    g.connect(this.fx!);
    n.start(t);
  }

  flip() {
    if (!this.enabled || !this.ctx) return;
    const t = this.ctx.currentTime + 0.02;
    [523.25, 659.25, 783.99].forEach((f, i) => this.ping(f, t + i * 0.07, 0.05, 1.4));
  }
}

export const audio = new AudioEngine();
