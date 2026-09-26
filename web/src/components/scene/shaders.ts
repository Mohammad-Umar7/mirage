// GLSL for the account nodes. One draw call for every account.

export const nodeVertex = /* glsl */ `
  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uScale;
  uniform float uFocus;
  uniform float uAperture;
  uniform vec3  uWaveOrigin;
  uniform float uWaveT;
  uniform float uDim;

  attribute float aSeed;
  attribute float aSize;
  attribute float aThreatFrom;
  attribute float aThreatTo;
  attribute float aThreatStart;
  attribute float aOrgFrom;
  attribute float aOrgTo;
  attribute float aOrgStart;
  attribute float aPulse;
  attribute float aBirth;

  varying float vThreat;
  varying float vOrganic;
  varying float vPulse;
  varying float vSeed;
  varying float vPx;
  varying float vCoc;
  varying float vAlpha;
  varying float vWave;

  void main() {
    float tk = clamp((uTime - aThreatStart) / 1.6, 0.0, 1.0);
    tk = tk * tk * (3.0 - 2.0 * tk);
    vThreat = mix(aThreatFrom, aThreatTo, tk);
    float ok = clamp((uTime - aOrgStart) / 1.2, 0.0, 1.0);
    vOrganic = mix(aOrgFrom, aOrgTo, ok);
    float age = uTime - aPulse;
    vPulse = age > 0.0 ? exp(-age * 2.4) : 0.0;
    float born = clamp((uTime - aBirth) / 1.4, 0.0, 1.0);
    born = born * born * (3.0 - 2.0 * born);

    vec3 p = position;
    // barely-there breathing so the void feels alive
    p += 0.32 * vec3(sin(uTime * 0.31 + aSeed * 41.0), cos(uTime * 0.27 + aSeed * 29.0), sin(uTime * 0.23 + aSeed * 17.0));

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float depth = max(-mv.z, 1.0);

    // detection shockwave sweeping outward
    float waveAge = uTime - uWaveT;
    float wave = 0.0;
    if (waveAge > 0.0 && waveAge < 3.2) {
      float r = waveAge * 175.0;
      float d = distance(p, uWaveOrigin);
      float q = (d - r) / 16.0;
      wave = exp(-q * q) * (1.0 - waveAge / 3.2);
    }
    vWave = wave;

    // depth of field: circle of confusion grows away from the focal plane
    float coc = clamp(abs(depth - uFocus) * uAperture, 0.0, 7.0);
    vCoc = coc;

    float base = aSize * (1.0 + vThreat * 0.3 + vOrganic * 0.25) * (1.0 + vPulse * 0.8 + wave * 1.8);
    float px = base * uScale * min(320.0 / depth, 2.6);
    px += coc * 1.6;
    px *= born;
    vPx = px;
    gl_PointSize = clamp(px * uPixelRatio, 0.0, 180.0);
    vAlpha = born * (1.0 / (1.0 + coc * coc * 0.16)) * (1.0 + wave * 1.4) * uDim;
    vSeed = aSeed;
    gl_Position = projectionMatrix * mv;
  }
`;

export const nodeFragment = /* glsl */ `
  uniform vec3 uGold;
  uniform vec3 uAmber;
  uniform vec3 uRed;
  uniform vec3 uRedGlow;
  uniform float uIconPx;
  uniform float uPass; // 0 = additive pass (gold), 1 = alpha-blended pass (flagged red)

  varying float vThreat;
  varying float vOrganic;
  varying float vPulse;
  varying float vSeed;
  varying float vPx;
  varying float vCoc;
  varying float vAlpha;
  varying float vWave;

  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    uv.y = -uv.y;
    float d = length(uv);
    if (d > 0.5) discard;

    vec3 base = mix(uGold, uAmber, smoothstep(0.35, 0.95, vSeed));
    base = mix(base, vec3(1.0, 0.86, 0.58), vOrganic * 0.35);
    float threat = smoothstep(0.08, 0.85, vThreat);
    vec3 col = mix(base, uRed, threat);
    vec3 glow = mix(base, uRedGlow, threat);

    // soft glowing disc (bokeh-soft when out of focus)
    float soft = clamp(vCoc / 4.0, 0.0, 1.0);
    float core = smoothstep(0.5, 0.0, d);
    float halo = pow(core, mix(2.4, 1.1, soft));
    float spark = pow(core, mix(9.0, 2.5, soft));

    // close to the camera the node becomes a person inside a thin ring
    float icon = smoothstep(uIconPx, uIconPx * 1.9, vPx) * (1.0 - smoothstep(0.8, 2.6, vCoc));
    float ring = 1.0 - smoothstep(0.0, 0.03, abs(d - 0.43));
    float head = 1.0 - smoothstep(0.0, 0.028, length(uv - vec2(0.0, 0.1)) - 0.085);
    vec2 b = (uv - vec2(0.0, -0.215)) / vec2(0.19, 0.165);
    float bodyD = (length(b) - 1.0) * 0.165;
    float body = (1.0 - smoothstep(0.0, 0.026, bodyD)) * step(-0.215, uv.y) * step(d, 0.4);
    float glyph = max(head, body);

    // flagged accounts pack densely: thinner halos keep the cluster readable
    // as individual red points (bloom supplies the collective glow)
    float haloK = 1.0 - 0.55 * threat;
    float glowA = halo * 0.5 * haloK + spark * 0.95;
    vec3 c = glow * halo * 0.55 * haloK + col * spark * 1.25;
    vec3 iconCol = col * (ring * 1.35 + glyph * 1.2) + glow * halo * 0.22;
    float iconA = clamp(ring * 0.95 + glyph * 0.9 + halo * 0.22, 0.0, 1.0);
    c = mix(c, iconCol, icon);
    float a = mix(glowA, iconA, icon);

    // activity flashes and the shockwave
    c += glow * (vPulse * 0.9 + vWave * 1.6) * spark;

    // Flagged accounts move to an alpha-blended pass: additive blending of a
    // dense cluster always saturates to white, alpha blending stays red while
    // HDR values still feed the bloom.
    float redW = smoothstep(0.3, 0.72, threat);
    if (uPass < 0.5) {
      float w = 1.0 - redW;
      if (w < 0.004) discard;
      gl_FragColor = vec4(c, a * vAlpha * w);
    } else {
      if (redW < 0.004) discard;
      float shape = mix(clamp(spark * 1.15 + halo * 0.28, 0.0, 1.0), iconA, icon);
      vec3 hot = mix(uRedGlow * 0.75, uRed * 1.45, spark) + vec3(0.25, 0.05, 0.04) * (vPulse + vWave) * spark;
      hot = mix(hot, uRed * (ring * 1.5 + glyph * 1.35) + uRedGlow * halo * 0.2, icon);
      gl_FragColor = vec4(hot, shape * vAlpha * redW);
    }
  }
`;

export const edgeVertex = /* glsl */ `
  attribute float aAlpha;
  attribute vec3 aColor;
  uniform float uDim;
  varying float vAlpha;
  varying vec3 vColor;
  varying float vDepth;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth = -mv.z;
    vAlpha = aAlpha * uDim;
    vColor = aColor;
    gl_Position = projectionMatrix * mv;
  }
`;

export const edgeFragment = /* glsl */ `
  varying float vAlpha;
  varying vec3 vColor;
  varying float vDepth;
  uniform float uFocus;
  void main() {
    float fade = 1.0 / (1.0 + pow(max(0.0, vDepth - uFocus) / 260.0, 2.0));
    gl_FragColor = vec4(vColor, vAlpha * fade);
  }
`;

export const shellVertex = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

export const shellFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec3 vNormal;
  varying vec3 vView;
  void main() {
    float rim = pow(1.0 - abs(dot(vNormal, vView)), 3.0);
    gl_FragColor = vec4(uColor * (0.35 + rim * 1.8), (rim * 0.9 + 0.04) * uOpacity);
  }
`;

export const haloVertex = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const haloFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  uniform float uTime;
  varying vec2 vUv;
  void main() {
    vec2 p = vUv - 0.5;
    float d = length(p) * 2.0;
    float rq = (d - 0.86) / 0.035;
    float ring = exp(-rq * rq);
    float fill = smoothstep(1.0, 0.0, d) * 0.06;
    float ang = atan(p.y, p.x);
    float dash = 0.55 + 0.45 * step(0.5, fract(ang * 6.0 / 3.14159 + uTime * 0.05));
    float a = (ring * dash + fill) * uOpacity;
    gl_FragColor = vec4(uColor, a);
  }
`;
