/* Ambient shader wall behind the gallery. fBm with domain warping in the
   Quilez style; cosine palette for cohesive color. Kept dark and slow so the
   tiles stay dominant. (Book of Shaders ch11/ch13 + ch06.) */

(function () {
  const canvas = document.getElementById('bg');
  const gl = canvas.getContext('webgl', { antialias: false, premultipliedAlpha: false });
  if (!gl) {
    document.body.style.background =
      'radial-gradient(ellipse at 30% 20%, #2a2144 0%, #0a0a12 70%)';
    return;
  }

  const vertSrc = `
    attribute vec2 a_pos;
    void main () { gl_Position = vec4(a_pos, 0.0, 1.0); }
  `;

  const fragSrc = `
    #ifdef GL_ES
    precision highp float;
    #endif
    uniform vec2  u_resolution;
    uniform float u_time;

    float rand (vec2 st) {
      return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
    }

    float noise (vec2 st) {
      vec2 i = floor(st);
      vec2 f = fract(st);
      float a = rand(i);
      float b = rand(i + vec2(1.0, 0.0));
      float c = rand(i + vec2(0.0, 1.0));
      float d = rand(i + vec2(1.0, 1.0));
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(a, b, u.x)
           + (c - a) * u.y * (1.0 - u.x)
           + (d - b) * u.x * u.y;
    }

    #define OCTAVES 5
    float fbm (vec2 st) {
      float v = 0.0;
      float a = 0.5;
      for (int i = 0; i < OCTAVES; i++) {
        v += a * noise(st);
        st *= 2.0;
        a  *= 0.5;
      }
      return v;
    }

    vec3 palette (float t) {
      vec3 a = vec3(0.08, 0.07, 0.14);
      vec3 b = vec3(0.28, 0.24, 0.40);
      vec3 c = vec3(1.00, 1.00, 1.00);
      vec3 d = vec3(0.00, 0.15, 0.35);
      return a + b * cos(6.28318 * (c * t + d));
    }

    void main () {
      vec2 st = gl_FragCoord.xy / u_resolution.xy;
      st.x *= u_resolution.x / u_resolution.y;
      st *= 1.4;

      float t = u_time * 0.025;

      vec2 q = vec2(
        fbm(st + vec2(0.0, t)),
        fbm(st + vec2(1.7, -t))
      );
      vec2 r = vec2(
        fbm(st + 3.5 * q + vec2(t * 0.5, 0.0)),
        fbm(st + 3.5 * q + vec2(0.0, t * 0.5))
      );
      float f = fbm(st + 3.5 * r);

      vec3 col = palette(f + t * 0.15);
      col *= 0.38 + 0.55 * smoothstep(0.0, 1.0, f);

      vec2 v = gl_FragCoord.xy / u_resolution.xy - 0.5;
      col *= 1.0 - dot(v, v) * 0.55;

      float grain = (rand(gl_FragCoord.xy + u_time) - 0.5) * 0.035;
      col += grain;

      gl_FragColor = vec4(col, 1.0);
    }
  `;

  function compile (type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  }

  const vs   = compile(gl.VERTEX_SHADER,   vertSrc);
  const fs   = compile(gl.FRAGMENT_SHADER, fragSrc);
  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(prog));
    return;
  }
  gl.useProgram(prog);

  const posBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.bufferData(gl.ARRAY_BUFFER,
    new Float32Array([-1,-1,  1,-1, -1, 1, -1, 1,  1,-1,  1, 1]),
    gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(prog, 'a_pos');
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

  const uRes  = gl.getUniformLocation(prog, 'u_resolution');
  const uTime = gl.getUniformLocation(prog, 'u_time');

  function resize () {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width  = Math.floor(window.innerWidth  * dpr);
    canvas.height = Math.floor(window.innerHeight * dpr);
    canvas.style.width  = window.innerWidth  + 'px';
    canvas.style.height = window.innerHeight + 'px';
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  window.addEventListener('resize', resize);
  resize();

  const t0 = performance.now();
  function frame () {
    const t = (performance.now() - t0) / 1000;
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, t);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    requestAnimationFrame(frame);
  }
  frame();
})();
