import { useEffect, useRef } from 'react'

// macOS 风格动态图案背景 (WebGL Canvas)
export default function MacPatternBackground() {
  const containerRef = useRef(null)

  useEffect(() => {
    // =================================
    // 1. 图标库
    // =================================
    const icons = [
      `<svg viewBox="0 0 64 64"><rect x="5" y="8" width="54" height="48" stroke="black" fill="none" stroke-width="4"/><path d="M32 8V56" stroke="black" stroke-width="3"/><circle cx="22" cy="27" r="4"/><circle cx="42" cy="27" r="4"/><path d="M18 43 Q32 50 46 43" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M36 14 C32 8 38 4 43 5 C43 12 39 16 36 14 M32 20 C20 15 10 27 15 43 C20 57 30 54 32 48 C35 55 46 57 51 42 C55 30 45 17 32 20Z" fill="black"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M18 18 H46 L42 55 H22Z" fill="none" stroke="black" stroke-width="4"/><path d="M15 18 H49" stroke="black" stroke-width="5"/><path d="M26 10 H38" stroke="black" stroke-width="5"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M6 18 H26 L32 25 H58 V52 H6Z" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><rect x="8" y="8" width="48" height="48" fill="none" stroke="black" stroke-width="4"/><rect x="18" y="10" width="28" height="14" fill="black"/><rect x="20" y="36" width="24" height="14" fill="none" stroke="black" stroke-width="3"/></svg>`,
      `<svg viewBox="0 0 64 64"><rect x="8" y="18" width="48" height="32" fill="none" stroke="black" stroke-width="4"/><circle cx="22" cy="34" r="8" fill="none" stroke="black" stroke-width="3"/><line x1="34" y1="34" x2="50" y2="34" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><rect x="16" y="28" width="32" height="24" fill="none" stroke="black" stroke-width="4"/><rect x="22" y="10" width="20" height="18" fill="none" stroke="black" stroke-width="4"/><rect x="8" y="22" width="48" height="20" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M20 8 L34 20 L28 28 C32 38 40 42 48 44 L56 36 L64 50 C50 62 18 44 8 18Z" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><rect x="8" y="16" width="48" height="34" fill="none" stroke="black" stroke-width="4"/><path d="M10 18 L32 38 L54 18" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><rect x="12" y="6" width="40" height="52" fill="none" stroke="black" stroke-width="4"/><rect x="20" y="14" width="24" height="10" fill="black"/><circle cx="22" cy="34" r="3"/><circle cx="32" cy="34" r="3"/><circle cx="42" cy="34" r="3"/><circle cx="22" cy="45" r="3"/><circle cx="32" cy="45" r="3"/><circle cx="42" cy="45" r="3"/></svg>`,
      `<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="24" fill="none" stroke="black" stroke-width="4"/><path d="M32 12 V32 L46 40" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="25" fill="none" stroke="black" stroke-width="4"/><path d="M7 32 H57 M32 7 C20 20 20 44 32 57 M32 7 C44 20 44 44 32 57" fill="none" stroke="black" stroke-width="3"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M10 40 L40 10 L54 24 L24 54Z" fill="none" stroke="black" stroke-width="4"/><circle cx="46" cy="18" r="5"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M38 10 V42 C25 38 20 46 26 52 C36 58 44 48 44 40 V18 L54 14" fill="none" stroke="black" stroke-width="5"/></svg>`,
      `<svg viewBox="0 0 64 64"><rect x="8" y="18" width="48" height="34" fill="none" stroke="black" stroke-width="4"/><circle cx="32" cy="35" r="10" fill="none" stroke="black" stroke-width="4"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M8 30 L32 8 L56 30 V56 H8Z" fill="none" stroke="black" stroke-width="4"/><rect x="25" y="38" width="14" height="18"/></svg>`,
      `<svg viewBox="0 0 64 64"><circle cx="32" cy="22" r="16"/><rect x="27" y="36" width="10" height="20"/></svg>`,
      `<svg viewBox="0 0 64 64"><path d="M10 38 L18 22 H44 L54 38 V50 H10Z" fill="none" stroke="black" stroke-width="4"/><circle cx="20" cy="50" r="5"/><circle cx="46" cy="50" r="5"/></svg>`
    ]

    function svgIcon(body) {
      return `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">${body}</svg>`
    }

    const shapes = [
      () => svgIcon(`<rect x="15" y="20" width="34" height="30" fill="none" stroke="black" stroke-width="4"/><line x1="32" y1="20" x2="32" y2="10" stroke="black" stroke-width="4"/><circle cx="32" cy="8" r="3"/><circle cx="25" cy="32" r="4"/><circle cx="39" cy="32" r="4"/>`),
      () => svgIcon(`<path d="M15 30 L10 18 L22 22 C32 14 48 20 50 38 C45 52 20 54 15 30Z" fill="none" stroke="black" stroke-width="4"/><circle cx="34" cy="32" r="3"/>`),
      () => svgIcon(`<path d="M15 20 L18 8 L30 18 L46 18 L54 8 L50 42 C45 54 20 54 14 42Z" fill="none" stroke="black" stroke-width="4"/><circle cx="27" cy="32" r="3"/><circle cx="40" cy="32" r="3"/>`),
      () => svgIcon(`<path d="M32 8 C15 25 20 45 32 54 C44 45 49 25 32 8Z" fill="none" stroke="black" stroke-width="4"/><circle cx="32" cy="28" r="5"/>`),
      () => svgIcon(`<path d="M8 34 L56 18 L38 34 L56 50 L8 34Z" fill="none" stroke="black" stroke-width="4"/>`),
      () => svgIcon(`<rect x="10" y="18" width="44" height="32" fill="none" stroke="black" stroke-width="4"/><line x1="22" y1="18" x2="16" y2="8" stroke="black" stroke-width="4"/><line x1="42" y1="18" x2="48" y2="8" stroke="black" stroke-width="4"/>`),
      () => svgIcon(`<rect x="10" y="20" width="44" height="32" fill="none" stroke="black" stroke-width="4"/><circle cx="32" cy="36" r="8"/><line x1="15" y1="14" x2="50" y2="14" stroke="black" stroke-width="4"/>`),
      () => svgIcon(`<path d="M12 50 L18 30 L46 10 L54 18 L28 46Z" fill="none" stroke="black" stroke-width="4"/>`),
      () => svgIcon(`<circle cx="26" cy="26" r="16" fill="none" stroke="black" stroke-width="4"/><line x1="38" y1="38" x2="54" y2="54" stroke="black" stroke-width="5"/>`),
      () => svgIcon(`<rect x="15" y="28" width="34" height="26" fill="none" stroke="black" stroke-width="4"/><path d="M22 28 V18 C22 5 42 5 42 18 V28" fill="none" stroke="black" stroke-width="4"/>`),
      () => svgIcon(`<rect x="10" y="14" width="44" height="40" fill="none" stroke="black" stroke-width="4"/><line x1="10" y1="26" x2="54" y2="26" stroke="black" stroke-width="4"/>`),
      () => svgIcon(`<circle cx="20" cy="30" r="12" fill="none" stroke="black" stroke-width="4"/><line x1="30" y1="30" x2="55" y2="30" stroke="black" stroke-width="5"/>`),
      () => svgIcon(`<path d="M8 32 C20 10 44 10 56 32 C44 54 20 54 8 32Z" fill="none" stroke="black" stroke-width="4"/><circle cx="32" cy="32" r="8"/>`)
    ]

    const generatedIcons = []
    for (let i = 0; i < 200; i++) {
      const shape = shapes[i % shapes.length]
      const svg = shape().replace('<svg', '<svg transform="scale(1.0)"')
      generatedIcons.push(svg)
    }
    const allIcons = [...icons, ...generatedIcons]

    // 时钟路径
    function getDigitPath(num, x, y) {
      const w = 20, h = 24, hw = 12
      const paths = [
        `M${x},${y} H${x + w} V${y + h} H${x} Z`,
        `M${x + w / 2},${y} V${y + h}`,
        `M${x},${y} H${x + w} V${y + hw} H${x} V${y + h} H${x + w}`,
        `M${x},${y} H${x + w} V${y + hw} H${x} M${x + w},${y + hw} V${y + h} H${x}`,
        `M${x},${y} V${y + hw} H${x + w} V${y} V${y + h}`,
        `M${x + w},${y} H${x} V${y + hw} H${x + w} V${y + h} H${x}`,
        `M${x + w},${y} H${x} V${y + h} H${x + w} V${y + hw} H${x}`,
        `M${x},${y} H${x + w} V${y + h}`,
        `M${x},${y} H${x + w} V${y + h} H${x} Z M${x},${y + hw} H${x + w}`,
        `M${x + w},${y + h} V${y} H${x} V${y + hw} H${x + w}`
      ]
      return paths[num]
    }

    function getClockPath(date) {
      const h = date.getHours().toString().padStart(2, '0')
      const m = date.getMinutes().toString().padStart(2, '0')
      return `${getDigitPath(+h[0], 8, 4)} ${getDigitPath(+h[1], 36, 4)} ${getDigitPath(+m[0], 8, 36)} ${getDigitPath(+m[1], 36, 36)}`
    }

    // 预加载图标
    const tile = document.createElement('canvas')
    tile.width = 512
    tile.height = 512
    const tctx = tile.getContext('2d')
    const loadedIcons = []
    let iconsReady = false

    Promise.all(allIcons.map(svg => {
      return new Promise(resolve => {
        let svgMod = svg
          .replace(/stroke-width="[0-9.]+"/g, 'stroke-width="5" stroke-dasharray="0 8" stroke-linecap="round"')
          .replace(/fill="black"/g, 'fill="none"')
        if (!svgMod.includes('xmlns')) {
          svgMod = svgMod.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
        }
        const img = new Image()
        img.onload = () => resolve(img)
        img.onerror = () => resolve(img)
        const blob = new Blob([svgMod], { type: 'image/svg+xml' })
        img.src = URL.createObjectURL(blob)
      })
    })).then(imgs => {
      loadedIcons.push(...imgs)
      iconsReady = true
    })

    let lastMinute = -1

    function updateTilePattern(now) {
      if (!iconsReady) return
      const currentMinute = now.getMinutes()
      if (currentMinute === lastMinute) return
      lastMinute = currentMinute

      tctx.clearRect(0, 0, tile.width, tile.height)
      const gap = 85
      let index = 0
      const clockPath2D = new Path2D(getClockPath(now))

      for (let y = 10; y < 512 + gap; y += gap) {
        const offsetX = (Math.floor(y / gap) % 2 === 0) ? 0 : gap / 2
        for (let x = 10 - offsetX; x < 512 + gap; x += gap) {
          if (index % 11 === 5) {
            tctx.save()
            tctx.translate(x, y)
            tctx.scale(46 / 64, 46 / 64)
            tctx.lineWidth = 5
            tctx.lineCap = 'round'
            tctx.setLineDash([0, 8])
            tctx.strokeStyle = 'black'
            tctx.stroke(clockPath2D)
            tctx.restore()
          } else {
            const img = loadedIcons[index % loadedIcons.length]
            if (img && img.width > 0) {
              tctx.globalAlpha = 1.0
              tctx.drawImage(img, x, y, 46, 46)
            }
          }
          index++
        }
      }
    }

    // =================================
    // 2. WebGL 渲染
    // =================================
    const glCanvas = document.createElement('canvas')
    glCanvas.style.cssText = 'width:100%;height:100%;display:block;position:absolute;top:0;left:0;z-index:0'
    containerRef.current.appendChild(glCanvas)

    const gl = glCanvas.getContext('webgl', { antialias: true })
    function resizeGL() {
      glCanvas.width = innerWidth
      glCanvas.height = innerHeight
      gl.viewport(0, 0, glCanvas.width, glCanvas.height)
    }
    window.addEventListener('resize', resizeGL)
    resizeGL()

    const vertexShader = `
attribute vec2 position;
varying vec2 uv;
void main(){
    uv=position*0.5+0.5;
    gl_Position=vec4(position,0,1);
}`

    const fragmentShader = `
precision highp float;
uniform sampler2D tex;
uniform float time;
uniform float u_timeOfDay;
uniform vec2 resolution;
varying vec2 uv;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main(){
    vec2 p=uv;
    p.x*=resolution.x/resolution.y;
    
    float angle=0.55;
    float s=sin(angle), c=cos(angle);
    p=mat2(c,-s,s,c)*p;
    
    p*=1.7;
    p.x+=time*0.06;
    p.y-=time*0.06;
    
    float iconAlpha=texture2D(tex,fract(p)).a;
    float shadowAlpha=texture2D(tex,fract(p+vec2(-0.015,0.015))).a;
    
    float hue = fract(u_timeOfDay / 300.0);
    vec3 bgColor     = hsv2rgb(vec3(hue, 0.56, 0.73));
    vec3 shadowColor = hsv2rgb(vec3(hue, 0.63, 0.65));
    vec3 iconColor   = hsv2rgb(vec3(hue, 0.79, 0.53));
    
    vec3 finalColor=bgColor;
    finalColor=mix(finalColor,shadowColor,shadowAlpha*0.8);
    finalColor=mix(finalColor,iconColor,iconAlpha);
    
    float dist=length(uv-0.5);
    finalColor*=smoothstep(0.9,0.2,dist)*0.15+0.85;
    
    gl_FragColor=vec4(finalColor,1.0);
}`

    function createShader(type, source) {
      const s = gl.createShader(type)
      gl.shaderSource(s, source)
      gl.compileShader(s)
      return s
    }

    const program = gl.createProgram()
    gl.attachShader(program, createShader(gl.VERTEX_SHADER, vertexShader))
    gl.attachShader(program, createShader(gl.FRAGMENT_SHADER, fragmentShader))
    gl.linkProgram(program)
    gl.useProgram(program)

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW)

    const pos = gl.getAttribLocation(program, 'position')
    gl.enableVertexAttribArray(pos)
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0)

    const texture = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)

    const timeLoc = gl.getUniformLocation(program, 'time')
    const timeOfDayLoc = gl.getUniformLocation(program, 'u_timeOfDay')
    const resolutionLoc = gl.getUniformLocation(program, 'resolution')

    let start = performance.now()
    let animId

    function animate() {
      const t = (performance.now() - start) / 1000
      const now = new Date()

      updateTilePattern(now)

      if (iconsReady) {
        const timeOfDay = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds() + now.getMilliseconds() / 1000

        gl.bindTexture(gl.TEXTURE_2D, texture)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, tile)

        gl.uniform1f(timeLoc, t)
        gl.uniform1f(timeOfDayLoc, timeOfDay)
        gl.uniform2f(resolutionLoc, glCanvas.width, glCanvas.height)

        gl.drawArrays(gl.TRIANGLES, 0, 6)
      }

      animId = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resizeGL)
      if (glCanvas.parentNode) glCanvas.parentNode.removeChild(glCanvas)
    }
  }, [])

  return <div ref={containerRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', overflow: 'hidden' }} />
}
