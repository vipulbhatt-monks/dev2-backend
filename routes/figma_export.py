from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import httpx
import json
import re
import uuid
import time
import asyncio
from services.ai_service import generate_text

router = APIRouter(prefix="/figma", tags=["figma"])

# ================================================================
# WEBSOCKET CONNECTION MANAGER
# ================================================================
class ConnectionManager:
    def __init__(self):
        self.active: dict[WebSocket, dict] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active[ws] = { "connected_at": time.time() }
        print(f"[WS] Plugin connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.pop(ws, None)
        print(f"[WS] Plugin disconnected. Total: {len(self.active)}")

    async def send(self, ws: WebSocket, data: dict):
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            self.disconnect(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self.active.keys()):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()


# ================================================================
# WS ENDPOINT  —  ws://localhost:8000/figma/ws
# ================================================================
@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("type") == "ping":
                await manager.send(ws, { "type": "pong" })
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        print(f"[WS] Error: {e}")
        manager.disconnect(ws)


# ================================================================
# /figma/push
# ================================================================
class FigmaPushRequest(BaseModel):
    appName: str
    screens: list
    figmaToken: str
    fileId: str

@router.post("/push")
async def push_to_figma(request: FigmaPushRequest):
    headers = { "X-Figma-Token": request.figmaToken, "Content-Type": "application/json" }
    base_url = f"https://api.figma.com/v1/files/{request.fileId}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(base_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Figma API Error: {resp.text}")
            return { "success": True, "message": f"Initialized push for {request.appName}." }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================
# /figma/generate-schema
# ================================================================
class FigmaSchemaRequest(BaseModel):
    html: str | None = None
    title: str | None = None
    screens: list[dict] | None = None

FIGMA_BRIDGE_SYSTEM_PROMPT = """
You are an expert Figma schema generator. Convert HTML/CSS/designs to pixel-perfect Figma JSON for 1:1 rendering.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Output ONLY valid JSON. No markdown, no explanation, no code fences.
- Root must be type "FRAME" with explicit width and height (the canvas/screen size).
- Every px value must be a plain number — never a string like "320px".
- Colors: use hex (#RRGGBB), rgba(r,g,b,a) — NEVER CSS variables or named colors except via the list below.
- Reproduce ALL visual details: gradients, shadows, glows, blurs, rotation, opacity, per-corner radius, etc.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPLETE NODE SCHEMA (safe subset)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  // ── Identity ─────────────────────────────────
  "type": "FRAME|SECTION|GROUP|COMPONENT|TEXT|RECTANGLE|ELLIPSE|LINE|IMAGE|VECTOR|POLYGON|STAR|BUTTON|INPUT|CARD|NAVBAR|BADGE|AVATAR|DIVIDER|ICON",
  "name": "string",

  // ── Size & Position ───────────────────────────
  "width": number,           // always set on frames & rects
  "height": number,          // always set on frames & rects
  "x": number,               // position within parent (NONE layout only)
  "y": number,
  "rotation": number,        // degrees, clockwise. e.g. -12 for slight tilt
  "opacity": number,         // 0–1
  "visible": boolean,        // default true
  "locked": boolean,

  // ── Auto Layout ───────────────────────────────
  "layoutMode": "HORIZONTAL|VERTICAL|NONE",
  "primaryAxisSizingMode": "FIXED|AUTO",
  "counterAxisSizingMode": "FIXED|AUTO",
  "primaryAxisAlignItems": "MIN|CENTER|MAX|SPACE_BETWEEN",
  "counterAxisAlignItems": "MIN|CENTER|MAX|BASELINE",
  "paddingTop": number,
  "paddingBottom": number,
  "paddingLeft": number,
  "paddingRight": number,
  "itemSpacing": number,     // gap between children
  "wrap": boolean,           // flex-wrap
  "counterAxisSpacing": number,

  // Absolute positioning within an auto-layout frame
  "layoutPositioning": "AUTO|ABSOLUTE",   // use ABSOLUTE for overlays/floating elements
  "absolutePosition": true,               // alias for layoutPositioning: "ABSOLUTE"

  // Child sizing within parent auto-layout
  "layoutGrow": 0|1,
  "layoutAlign": "INHERIT|STRETCH|MIN|CENTER|MAX",
  "minWidth": number, "maxWidth": number,
  "minHeight": number, "maxHeight": number,

  // ── Clipping ──────────────────────────────────
  "clipsContent": boolean,   // true = overflow hidden
  "overflow": "hidden",      // alias for clipsContent: true

  // ── Fills ─────────────────────────────────────
  // Option A: array of fill objects (preferred for multiple fills)
  "fills": [
    // Solid fill
    { "type": "SOLID", "color": {"r":0-1,"g":0-1,"b":0-1}, "opacity": 0-1 },

    // Linear gradient with angle (0=up, 90=right, 135=bottom-right, 180=down)
    {
      "type": "GRADIENT_LINEAR",
      "gradientAngle": 135,
      "gradientStops": [
        { "color": {"r":0.4,"g":0.2,"b":1,"a":1}, "position": 0 },
        { "color": {"r":0.1,"g":0.6,"b":1,"a":1}, "position": 1 }
      ]
    },

    // Radial gradient
    {
      "type": "GRADIENT_RADIAL",
      "gradientAngle": 0,
      "gradientStops": [
        { "color": {"r":1,"g":1,"b":1,"a":0.3}, "position": 0 },
        { "color": {"r":1,"g":1,"b":1,"a":0},   "position": 1 }
      ]
    },

    // Image fill
    { "type": "IMAGE", "scaleMode": "FILL|FIT|CROP|TILE", "src": "https://..." }
  ],

  // Option B: single fill color shorthand
  "fill": "#hexcolor or rgba(...)",
  "background": "#hexcolor",

  // ── Strokes / Borders ─────────────────────────
  "strokes": [
    { "type": "SOLID", "color": {"r":0-1,"g":0-1,"b":0-1}, "opacity": 0-1 }
  ],
  "strokeWeight": number,      // uniform weight
  "strokeAlign": "INSIDE|OUTSIDE|CENTER",
  "strokeCap": "NONE|ROUND|SQUARE",
  "strokeJoin": "MITER|ROUND|BEVEL",
  "dashPattern": [number, number],  // e.g. [4, 4] for dashed

  // Shorthand for single-color border
  "stroke": "#hex or rgba(...)",
  "borderColor": "#hex",
  "borderWidth": number,

  // Per-side stroke weights (for border-top, border-bottom only, etc.)
  "strokeTopWeight": number,
  "strokeRightWeight": number,
  "strokeBottomWeight": number,
  "strokeLeftWeight": number,

  // Border shorthand strings (e.g. "1px solid #E5E7EB")
  "borderBottom": "1px solid #E5E7EB",
  "borderTop": "1px solid #E5E7EB",

  // ── Corners ───────────────────────────────────
  "cornerRadius": number,          // uniform radius
  "topLeftRadius": number,         // per-corner overrides
  "topRightRadius": number,
  "bottomLeftRadius": number,
  "bottomRightRadius": number,
  "cornerSmoothing": number,       // 0–1, use 0.6 for Apple/iOS squircle look

  // ── Effects ───────────────────────────────────
  "effects": [
    // Drop shadow (standard box-shadow)
    {
      "type": "DROP_SHADOW",
      "color": {"r":0,"g":0,"b":0,"a":0.15},
      "offset": {"x":0,"y":4},
      "radius": 16,
      "spread": 0,
      "visible": true,
      "blendMode": "NORMAL"
    },
    // Inner shadow
    {
      "type": "INNER_SHADOW",
      "color": {"r":0,"g":0,"b":0,"a":0.1},
      "offset": {"x":0,"y":2},
      "radius": 8,
      "spread": 0,
      "visible": true
    },
    // Layer blur (frosted glass)
    { "type": "LAYER_BLUR", "radius": 12, "visible": true },
    // Background blur
    { "type": "BACKGROUND_BLUR", "radius": 20, "visible": true }
  ],

  // Shorthand glows (added to effects array automatically)
  "glow": {
    "color": "#6366F1",
    "opacity": 0.5,
    "radius": 24,
    "spread": 0
  },
  "outerGlow": { "color": "#FF0080", "opacity": 0.6, "radius": 30 },
  "innerGlow":  { "color": "#FFFFFF", "opacity": 0.3, "radius": 12 },

  // Shorthand blur
  "blur": number,            // layer blur radius
  "backgroundBlur": number,  // background blur radius (frosted glass)

  // Shorthand box-shadow strings
  "boxShadow": "0 4px 16px rgba(0,0,0,0.12)",
  "shadow": "0 8px 32px rgba(99,102,241,0.3)",

  // ── Blend Mode ────────────────────────────────
  "blendMode": "NORMAL|MULTIPLY|SCREEN|OVERLAY|DARKEN|LIGHTEN|COLOR_DODGE|COLOR_BURN|HARD_LIGHT|SOFT_LIGHT|DIFFERENCE|EXCLUSION|HUE|SATURATION|COLOR|LUMINOSITY",

  // ── Constraints (pin behavior on resize) ──────
  "constraints": {
    "horizontal": "LEFT|RIGHT|CENTER|SCALE|STRETCH",
    "vertical":   "TOP|BOTTOM|CENTER|SCALE|STRETCH"
  },

  // ── Children ──────────────────────────────────
  "children": [...]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEXT NODE SCHEMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "type": "TEXT",
  "name": "string",
  "characters": "The text content",
  "fontSize": 16,
  "fontFamily": "Inter",
  "fontStyle": "Regular|Medium|Semi Bold|Bold|Light|Thin|Extra Bold|Black|Italic|Bold Italic",
  "color": "#hex or rgba(...)",
  "fills": [...],                    // or use "color" shorthand
  "textAlignHorizontal": "LEFT|CENTER|RIGHT|JUSTIFIED",
  "textAlignVertical": "TOP|CENTER|BOTTOM",
  "lineHeight": 24,                  // pixels, or {"value":150,"unit":"PERCENT"}, or {"unit":"AUTO"}
  "letterSpacing": 0.5,              // pixels, or {"value":5,"unit":"PERCENT"}
  "textDecoration": "NONE|UNDERLINE|STRIKETHROUGH",
  "textCase": "ORIGINAL|UPPER|LOWER|TITLE",
  "textAutoResize": "NONE|WIDTH_AND_HEIGHT|HEIGHT",
  "paragraphSpacing": 8,
  "maxLines": 2,
  "truncation": true,                // adds ellipsis
  "width": number,                   // set when text has a fixed width
  "height": number,                  // set when text has fixed width AND height
  "opacity": 0-1,
  "rotation": number,

  // Mixed inline styles (bold word, colored span, etc.)
  "styleRuns": [
    { "length": 5, "fontStyle": "Bold", "color": "#FF0000" },
    { "length": 3, "fontStyle": "Regular" },
    { "length": 8, "fontSize": 24, "fills": [{"type":"SOLID","color":{"r":1,"g":0,"b":0}}] }
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ELLIPSE / CIRCLE NODE (for avatars, progress rings, dots)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "type": "ELLIPSE",
  "width": 48, "height": 48,
  "fill": "#6366F1",
  "arcData": { "startingAngle": 0, "endingAngle": 4.712 }  // for arcs/progress rings
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMAGE NODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "type": "IMAGE",
  "name": "Hero Image",
  "width": 400, "height": 240,
  "src": "https://images.unsplash.com/...",
  "scaleMode": "FILL",
  "cornerRadius": 12
}
Or as a fill on a FRAME/RECTANGLE:
"fills": [{ "type": "IMAGE", "src": "https://...", "scaleMode": "FILL" }]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VECTOR / SVG PATH NODE (pixel-perfect icons)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "type": "VECTOR",
  "name": "Arrow Icon",
  "width": 24, "height": 24,
  "svgPath": "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
  "fill": "#6366F1"
}
Or with multiple paths:
"vectorPaths": [
  { "windingRule": "NONZERO", "data": "M 0 0 L 24 0 L 24 24 Z" }
]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL WORKAROUNDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NEVER use type "INPUT" for text fields — use FRAME workaround:
{
  "type": "FRAME", "name": "Input Field",
  "layoutMode": "HORIZONTAL", "counterAxisAlignItems": "CENTER",
  "paddingLeft": 12, "paddingRight": 12, "paddingTop": 10, "paddingBottom": 10,
  "width": 272, "height": 40,
  "fills": [{"type":"SOLID","color":{"r":1,"g":1,"b":1}}],
  "cornerRadius": 8,
  "strokes": [{"type":"SOLID","color":{"r":0.8,"g":0.8,"b":0.8}}],
  "strokeWeight": 1, "strokeAlign": "INSIDE",
  "children": [{
    "type": "TEXT", "characters": "Placeholder text",
    "fontSize": 14, "color": "#9CA3AF"
  }]
}

2. NEVER use type "BUTTON" — use FRAME workaround:
{
  "type": "FRAME", "name": "Button",
  "layoutMode": "HORIZONTAL",
  "primaryAxisAlignItems": "CENTER", "counterAxisAlignItems": "CENTER",
  "width": 200, "height": 44,
  "fills": [{"type":"SOLID","color":{"r":0.388,"g":0.4,"b":0.945}}],
  "cornerRadius": 8,
  "children": [{"type":"TEXT","characters":"Get Started","fontStyle":"Semi Bold","fontSize":15,"color":"#FFFFFF"}]
}

3. CENTERED TEXT: Whenever CSS has text-align:center, EVERY text child MUST have "textAlignHorizontal": "CENTER".

4. SIZING: Always set explicit width AND height on FRAME nodes. Never rely on auto-sizing for frames.

5. NEVER use layoutGrow — the renderer ignores it. Use explicit width/height.

6. STROKES: Always set "strokeAlign": "INSIDE" to prevent dimensions expanding.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROTATION (tilted, angled, slanted elements)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Use "rotation": <degrees> on any node (clockwise positive, counter-clockwise negative)
- Tilted card: "rotation": -5
- Diagonal divider: "rotation": 45
- Slight text tilt: "rotation": -3
- Elements with rotation should have explicit x/y and layoutPositioning: "ABSOLUTE" if inside auto-layout

Example — tilted decorative rectangle:
{
  "type": "RECTANGLE", "name": "Tilted BG",
  "width": 400, "height": 400,
  "fill": "rgba(99,102,241,0.1)",
  "cornerRadius": 40,
  "rotation": -15,
  "x": -80, "y": -80,
  "layoutPositioning": "ABSOLUTE"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRADIENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Always use "gradientAngle" (CSS convention: 0=up, 90=right, 180=down, 270=left).

Linear gradient (top to bottom):
{
  "type": "GRADIENT_LINEAR",
  "gradientAngle": 180,
  "gradientStops": [
    {"color": {"r":0.388,"g":0.4,"b":0.945,"a":1}, "position": 0},
    {"color": {"r":0.612,"g":0.227,"b":0.875,"a":1}, "position": 1}
  ]
}

Diagonal gradient (top-left to bottom-right):
{
  "type": "GRADIENT_LINEAR",
  "gradientAngle": 135,
  "gradientStops": [
    {"color": {"r":1,"g":0.4,"b":0.6,"a":1}, "position": 0},
    {"color": {"r":0.4,"g":0.2,"b":1,"a":1}, "position": 1}
  ]
}

Radial gradient (center glow):
{
  "type": "GRADIENT_RADIAL",
  "gradientAngle": 0,
  "gradientStops": [
    {"color": {"r":1,"g":1,"b":1,"a":0.4}, "position": 0},
    {"color": {"r":1,"g":1,"b":1,"a":0},   "position": 1}
  ]
}

Multi-stop gradient:
{
  "type": "GRADIENT_LINEAR",
  "gradientAngle": 90,
  "gradientStops": [
    {"color": {"r":1,"g":0.27,"b":0,"a":1}, "position": 0},
    {"color": {"r":1,"g":0.55,"b":0,"a":1}, "position": 0.5},
    {"color": {"r":1,"g":0.85,"b":0,"a":1}, "position": 1}
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GLOWS & ADVANCED SHADOWS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Outer glow (neon, glowing button):
"glow": { "color": "#6366F1", "opacity": 0.6, "radius": 24, "spread": 0 }

Outer neon glow (multiple shadows for intensity):
"effects": [
  {"type":"DROP_SHADOW","color":{"r":0.388,"g":0.4,"b":0.945,"a":0.8},"offset":{"x":0,"y":0},"radius":8,"spread":2},
  {"type":"DROP_SHADOW","color":{"r":0.388,"g":0.4,"b":0.945,"a":0.4},"offset":{"x":0,"y":0},"radius":24,"spread":0},
  {"type":"DROP_SHADOW","color":{"r":0.388,"g":0.4,"b":0.945,"a":0.2},"offset":{"x":0,"y":0},"radius":48,"spread":0}
]

Inner glow (glass/inset highlight):
"innerGlow": { "color": "#FFFFFF", "opacity": 0.3, "radius": 16 }

Colored drop shadow:
"effects": [
  {"type":"DROP_SHADOW","color":{"r":1,"g":0,"b":0.5,"a":0.4},"offset":{"x":0,"y":8},"radius":24,"spread":0}
]

Frosted glass (blur + semi-transparent fill):
{
  "type": "FRAME",
  "fills": [{"type":"SOLID","color":{"r":1,"g":1,"b":1},"opacity":0.15}],
  "backgroundBlur": 20,
  "strokes": [{"type":"SOLID","color":{"r":1,"g":1,"b":1},"opacity":0.3}],
  "strokeWeight": 1, "strokeAlign": "INSIDE"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURVED BORDERS & CORNER RADIUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pill / fully rounded: "cornerRadius": 999
Circle: use ELLIPSE type
Rounded top only: "topLeftRadius": 12, "topRightRadius": 12, "bottomLeftRadius": 0, "bottomRightRadius": 0
iOS-style squircle (smooth curves): "cornerRadius": 20, "cornerSmoothing": 0.6
Large card with gradient border:
{
  "type": "FRAME",
  "cornerRadius": 24,
  "strokes": [{"type":"GRADIENT_LINEAR","gradientAngle":135,
    "gradientStops":[{"color":{"r":1,"g":0.4,"b":0.8,"a":1},"position":0},{"color":{"r":0.4,"g":0.4,"b":1,"a":1},"position":1}]}],
  "strokeWeight": 2, "strokeAlign": "INSIDE"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE POSITIONING (overlapping, floating, layered elements)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When elements overlap (like a floating badge on a card, or decorative shapes behind content):
- Set parent frame with "layoutMode": "NONE" OR
- Set child with "layoutPositioning": "ABSOLUTE" inside an auto-layout frame
- Always set explicit x, y on absolutely positioned children

Example — card with floating badge:
{
  "type": "FRAME", "layoutMode": "VERTICAL", "width": 320, "height": 200,
  "children": [
    { "type": "TEXT", "characters": "Card Title" },
    {
      "type": "FRAME", "name": "Hot Badge",
      "layoutPositioning": "ABSOLUTE",
      "x": 260, "y": -10,
      "width": 48, "height": 24,
      "cornerRadius": 999,
      "fill": "#FF4444",
      "children": [{"type":"TEXT","characters":"HOT","fontSize":10,"color":"#FFFFFF","fontStyle":"Bold"}]
    }
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPACITY & BLEND MODES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Node opacity: "opacity": 0.5 (0=invisible, 1=fully opaque)
- Fill opacity: inside fills array: {"type":"SOLID","color":{...},"opacity":0.3}
- Blend mode on node: "blendMode": "MULTIPLY"
- Useful blend modes: MULTIPLY (darken), SCREEN (lighten), OVERLAY (contrast), SOFT_LIGHT

Example — overlay element:
{ "type": "RECTANGLE", "width": 400, "height": 400, "fill": "#000000", "opacity": 0.4, "blendMode": "MULTIPLY" }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PER-SIDE BORDERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bottom border only (like a tab underline):
{
  "strokes": [{"type":"SOLID","color":{"r":0.388,"g":0.4,"b":0.945}}],
  "strokeWeight": 2,
  "strokeAlign": "INSIDE",
  "strokeTopWeight": 0,
  "strokeRightWeight": 0,
  "strokeLeftWeight": 0,
  "strokeBottomWeight": 2
}

Or use shorthand:
"borderBottom": "2px solid #6366F1"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONVERSION RULES FROM HTML/CSS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CSS → Figma JSON mappings:

display:flex; flex-direction:row  → layoutMode: "HORIZONTAL"
display:flex; flex-direction:column → layoutMode: "VERTICAL"
justify-content:center            → primaryAxisAlignItems: "CENTER"
justify-content:space-between     → primaryAxisAlignItems: "SPACE_BETWEEN"
align-items:center                → counterAxisAlignItems: "CENTER"
align-items:flex-end              → counterAxisAlignItems: "MAX"
gap: 16px                         → itemSpacing: 16
padding: 24px                     → paddingTop/Bottom/Left/Right: 24
padding: 16px 24px                → paddingTop: 16, paddingBottom: 16, paddingLeft: 24, paddingRight: 24
border-radius: 50%                → ELLIPSE type (or cornerRadius: 999 for pill)
border-radius: 12px 0 12px 0      → topLeftRadius: 12, topRightRadius: 0, bottomRightRadius: 12, bottomLeftRadius: 0
box-shadow: 0 4px 24px rgba(0,0,0,0.1) → effects: [{type:"DROP_SHADOW",...}]
box-shadow: 0 0 20px #6366F1      → glow: {color:"#6366F1", radius:20}
backdrop-filter: blur(20px)       → backgroundBlur: 20
filter: blur(8px)                 → blur: 8
background: linear-gradient(135deg, ...) → fills: [{type:"GRADIENT_LINEAR", gradientAngle:135, ...}]
transform: rotate(-12deg)         → rotation: -12
position: absolute                → layoutPositioning: "ABSOLUTE" (with x, y)
overflow: hidden                  → clipsContent: true
opacity: 0.5                      → opacity: 0.5
margin-bottom: 16px               → use parent's itemSpacing: 16 instead
letter-spacing: 0.05em with 16px font → letterSpacing: 0.8 (px)
line-height: 1.5 with 16px font   → lineHeight: 24 (px)
font-weight: 600                  → fontStyle: "Semi Bold"
font-weight: 700                  → fontStyle: "Bold"
text-transform: uppercase         → textCase: "UPPER"
text-decoration: underline        → textDecoration: "UNDERLINE"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLOR CONVERSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hex to Figma RGB (divide each channel by 255):
#6366F1 → {"r":0.388,"g":0.4,"b":0.945}
#1F2937 → {"r":0.122,"g":0.161,"b":0.216}
#FFFFFF → {"r":1,"g":1,"b":1}
#000000 → {"r":0,"g":0,"b":0}
#10B981 → {"r":0.063,"g":0.725,"b":0.506}
#EF4444 → {"r":0.937,"g":0.267,"b":0.267}
#F59E0B → {"r":0.961,"g":0.620,"b":0.043}
#3B82F6 → {"r":0.231,"g":0.510,"b":0.965}

For rgba(99, 102, 241, 0.5) → {"r":0.388,"g":0.4,"b":0.945,"a":0.5}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPLEX EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXAMPLE 1 — Glassmorphism card with glow:
{
  "type": "FRAME", "name": "Glass Card",
  "width": 360, "height": 200, "cornerRadius": 20,
  "fills": [{"type":"SOLID","color":{"r":1,"g":1,"b":1},"opacity":0.12}],
  "backgroundBlur": 24,
  "strokes": [{"type":"SOLID","color":{"r":1,"g":1,"b":1},"opacity":0.25}],
  "strokeWeight": 1, "strokeAlign": "INSIDE",
  "glow": {"color":"#6366F1","opacity":0.3,"radius":40},
  "layoutMode": "VERTICAL", "padding": 24, "itemSpacing": 12
}

EXAMPLE 2 — Gradient button with neon glow:
{
  "type": "FRAME", "name": "Neon Button",
  "layoutMode": "HORIZONTAL",
  "primaryAxisAlignItems": "CENTER", "counterAxisAlignItems": "CENTER",
  "width": 200, "height": 48, "cornerRadius": 24,
  "fills": [{"type":"GRADIENT_LINEAR","gradientAngle":90,
    "gradientStops":[{"color":{"r":0.388,"g":0.4,"b":0.945,"a":1},"position":0},
                     {"color":{"r":0.612,"g":0.227,"b":0.875,"a":1},"position":1}]}],
  "effects": [
    {"type":"DROP_SHADOW","color":{"r":0.388,"g":0.4,"b":0.945,"a":0.7},"offset":{"x":0,"y":0},"radius":16,"spread":2},
    {"type":"DROP_SHADOW","color":{"r":0.388,"g":0.4,"b":0.945,"a":0.3},"offset":{"x":0,"y":4},"radius":32,"spread":0}
  ],
  "children": [{"type":"TEXT","characters":"Launch App","fontSize":16,"fontStyle":"Semi Bold","color":"#FFFFFF","letterSpacing":0.3}]
}

EXAMPLE 3 — Tilted decorative element:
{
  "type": "RECTANGLE", "name": "Decorative Blob",
  "width": 300, "height": 300, "cornerRadius": 80,
  "fills": [{"type":"GRADIENT_LINEAR","gradientAngle":135,
    "gradientStops":[{"color":{"r":0.388,"g":0.4,"b":0.945,"a":0.3},"position":0},
                     {"color":{"r":1,"g":0.4,"b":0.6,"a":0.1},"position":1}]}],
  "rotation": -25, "opacity": 0.8,
  "layoutPositioning": "ABSOLUTE", "x": -60, "y": -60
}

EXAMPLE 4 — Mixed text with inline styles (e.g. "Save 50% today"):
{
  "type": "TEXT",
  "characters": "Save 50% today",
  "fontSize": 24, "fontStyle": "Regular", "color": "#1F2937",
  "styleRuns": [
    {"length": 5, "fontStyle": "Regular"},
    {"length": 3, "fontStyle": "Bold", "color": "#EF4444", "fontSize": 28},
    {"length": 7, "fontStyle": "Regular"}
  ]
}

EXAMPLE 5 — Progress ring (arc ellipse):
{
  "type": "ELLIPSE", "name": "Progress Ring",
  "width": 80, "height": 80,
  "strokes": [{"type":"SOLID","color":{"r":0.388,"g":0.4,"b":0.945}}],
  "strokeWeight": 6, "strokeAlign": "INSIDE",
  "fills": [],
  "arcData": {"startingAngle": -1.5708, "endingAngle": 1.5708}
}

EXAMPLE 6 — Card height calculation:
Padding top 24 + icon 48 + gap 16 + title (fontSize 20, lineHeight 28) + gap 12 + body (3 lines × 20px + 2 × gap 4) + padding bottom 24
= 24 + 48 + 16 + 28 + 12 + (3×20 + 2×4) + 24 = 24+48+16+28+12+68+24 = 220px

EXAMPLE 7 — Tab bar with active indicator (bottom border):
{
  "type": "FRAME", "name": "Tab Active",
  "layoutMode": "VERTICAL", "primaryAxisAlignItems": "CENTER", "counterAxisAlignItems": "CENTER",
  "paddingBottom": 12, "paddingTop": 12, "paddingLeft": 16, "paddingRight": 16,
  "strokes": [{"type":"SOLID","color":{"r":0.388,"g":0.4,"b":0.945}}],
  "strokeWeight": 2, "strokeAlign": "INSIDE",
  "strokeTopWeight": 0, "strokeLeftWeight": 0, "strokeRightWeight": 0, "strokeBottomWeight": 2,
  "children": [{"type":"TEXT","characters":"Dashboard","fontSize":14,"fontStyle":"Semi Bold","color":"#6366F1"}]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIZING RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Root frame: always explicit width and height (screen dimensions, e.g. 390×844 for iPhone, 1440×900 for desktop)
2. All FRAME/RECTANGLE/ELLIPSE children: always explicit width and height
3. Height calculation for vertical auto-layout frames:
   totalHeight = paddingTop + paddingBottom + sum(childHeights) + (itemSpacing × (childCount - 1))
4. TEXT nodes with fixed width: set "width" and "textAutoResize": "HEIGHT" — do NOT set height
5. TEXT nodes free-floating: omit width and height entirely (auto-sizes)
6. TEXT nodes fixed box: set both width AND height AND "textAutoResize": "NONE"
7. When a container has children that overflow, ensure "clipsContent": true

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTO LAYOUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Every frame with children MUST declare layoutMode (HORIZONTAL, VERTICAL, or NONE)
- Use NONE only when children overlap or are absolutely positioned
- For overlapping elements: use layoutMode NONE on parent, set explicit x/y on ALL children
- For mostly-stacked with one floating badge: use VERTICAL on parent, ABSOLUTE on floating child
- Do NOT mix absolute children with auto-layout children unless required
- itemSpacing replaces margin-bottom/margin-top — do not use both

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRID LAYOUTS (CSS grid / flex-wrap) — READ THIS CAREFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Figma has NO native CSS grid. You MUST implement grids using one of these two methods:

METHOD A — layoutMode NONE with explicit x/y (REQUIRED for 2+ column grids):
- Set parent to "layoutMode": "NONE"
- Give EVERY child an explicit "x" and "y" and "width" and "height"
- Calculate positions manually: col index × (cardWidth + gap), row index × (cardHeight + gap)
- Parent height = rows × cardHeight + (rows-1) × rowGap + paddingTop + paddingBottom
- Parent width  = cols × cardWidth  + (cols-1) × colGap  + paddingLeft + paddingRight

METHOD B — HORIZONTAL layout with "wrap": true (only for same-height rows):
- Set parent "layoutMode": "HORIZONTAL", "wrap": true
- Set "itemSpacing" for column gap, "counterAxisSpacing" for row gap
- Each child must have explicit width and height

CRITICAL — 2-COLUMN GRID EXAMPLE (cards side by side, 2 rows):
Screen width 1440px, padding 80px each side → content width = 1280px
2 columns with 24px gap → cardWidth = (1280 - 24) / 2 = 628px
cardHeight (calculated from content) = e.g. 160px
rowGap = 24px

Parent grid container:
{
  "type": "FRAME", "name": "Card Grid",
  "layoutMode": "NONE",
  "width": 1280, "height": 368,
  "fills": [],
  "children": [
    { card with "x": 0,   "y": 0,   "width": 628, "height": 160 },
    { card with "x": 652, "y": 0,   "width": 628, "height": 160 },
    { card with "x": 0,   "y": 184, "width": 628, "height": 160 },
    { card with "x": 652, "y": 184, "width": 628, "height": 160 }
  ]
}
Note: x of col 2 = cardWidth + gap = 628 + 24 = 652
      y of row 2 = cardHeight + rowGap = 160 + 24 = 184
      Parent height = 2 × 160 + 1 × 24 = 344 (+ any padding)

FULL WORKED EXAMPLE — NVIDIA-style 2×2 card grid inside a page:
{
  "type": "FRAME", "name": "Page",
  "width": 1440, "height": 900,
  "layoutMode": "VERTICAL",
  "primaryAxisAlignItems": "MIN",
  "counterAxisAlignItems": "CENTER",
  "paddingTop": 40, "paddingBottom": 60,
  "paddingLeft": 80, "paddingRight": 80,
  "itemSpacing": 48,
  "fills": [{"type":"SOLID","color":{"r":0.07,"g":0.07,"b":0.07}}],
  "children": [
    {
      "type": "FRAME", "name": "Navbar",
      "layoutMode": "HORIZONTAL", "primaryAxisAlignItems": "SPACE_BETWEEN", "counterAxisAlignItems": "CENTER",
      "width": 1280, "height": 48, "fills": [],
      "children": [
        {"type":"TEXT","characters":"NVIDIA ENTERPRISE","fontSize":14,"color":"#FFFFFF","fontStyle":"Bold"},
        {"type":"TEXT","characters":"Solutions | Software | Infrastructure","fontSize":14,"color":"#CCCCCC"}
      ]
    },
    {
      "type": "FRAME", "name": "Hero Text",
      "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN", "counterAxisAlignItems": "CENTER",
      "width": 1280, "height": 80, "fills": [], "itemSpacing": 12,
      "children": [
        {"type":"TEXT","characters":"The Infrastructure of Intelligence","fontSize":48,"fontStyle":"Bold","color":"#76B900","textAlignHorizontal":"CENTER","width":1280},
        {"type":"TEXT","characters":"Scale your generative AI from prototype to production with NVIDIA AI Enterprise.","fontSize":16,"color":"#CCCCCC","textAlignHorizontal":"CENTER","width":700}
      ]
    },
    {
      "type": "FRAME", "name": "Card Grid",
      "layoutMode": "NONE",
      "width": 1280, "height": 344,
      "fills": [],
      "children": [
        {
          "type": "FRAME", "name": "Card - NVIDIA H100 GPU",
          "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
          "x": 0, "y": 0, "width": 628, "height": 160,
          "paddingTop": 24, "paddingBottom": 24, "paddingLeft": 24, "paddingRight": 24,
          "itemSpacing": 12,
          "cornerRadius": 8,
          "fills": [{"type":"SOLID","color":{"r":0.13,"g":0.13,"b":0.13}}],
          "children": [
            {"type":"TEXT","characters":"NVIDIA H100 GPU","fontSize":18,"fontStyle":"Semi Bold","color":"#76B900"},
            {"type":"TEXT","characters":"The world's most advanced chip for generative AI, featuring the Transformer Engine.","fontSize":14,"color":"#AAAAAA","width":580,"textAutoResize":"HEIGHT"}
          ]
        },
        {
          "type": "FRAME", "name": "Card - DGX Systems",
          "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
          "x": 652, "y": 0, "width": 628, "height": 160,
          "paddingTop": 24, "paddingBottom": 24, "paddingLeft": 24, "paddingRight": 24,
          "itemSpacing": 12,
          "cornerRadius": 8,
          "fills": [{"type":"SOLID","color":{"r":0.13,"g":0.13,"b":0.13}}],
          "children": [
            {"type":"TEXT","characters":"DGX Systems","fontSize":18,"fontStyle":"Semi Bold","color":"#76B900"},
            {"type":"TEXT","characters":"The blueprint for AI factories. Fully integrated hardware and software solutions.","fontSize":14,"color":"#AAAAAA","width":580,"textAutoResize":"HEIGHT"}
          ]
        },
        {
          "type": "FRAME", "name": "Card - NVIDIA AI Enterprise",
          "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
          "x": 0, "y": 184, "width": 628, "height": 160,
          "paddingTop": 24, "paddingBottom": 24, "paddingLeft": 24, "paddingRight": 24,
          "itemSpacing": 12,
          "cornerRadius": 8,
          "fills": [{"type":"SOLID","color":{"r":0.13,"g":0.13,"b":0.13}}],
          "children": [
            {"type":"TEXT","characters":"NVIDIA AI Enterprise","fontSize":18,"fontStyle":"Semi Bold","color":"#76B900"},
            {"type":"TEXT","characters":"An end-to-end, cloud-native suite of AI and data science software.","fontSize":14,"color":"#AAAAAA","width":580,"textAutoResize":"HEIGHT"}
          ]
        },
        {
          "type": "FRAME", "name": "Card - Omniverse",
          "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
          "x": 652, "y": 184, "width": 628, "height": 160,
          "paddingTop": 24, "paddingBottom": 24, "paddingLeft": 24, "paddingRight": 24,
          "itemSpacing": 12,
          "cornerRadius": 8,
          "fills": [{"type":"SOLID","color":{"r":0.13,"g":0.13,"b":0.13}}],
          "children": [
            {"type":"TEXT","characters":"Omniverse","fontSize":18,"fontStyle":"Semi Bold","color":"#76B900"},
            {"type":"TEXT","characters":"The platform for connecting and developing OpenUSD-based 3D pipelines.","fontSize":14,"color":"#AAAAAA","width":580,"textAutoResize":"HEIGHT"}
          ]
        }
      ]
    }
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT FIDELITY RULES — DO NOT HALLUCINATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ONLY render what is present in the HTML/design. Do NOT add sections, components, or
   content that does not exist in the source. If the HTML has 4 cards, output exactly 4 cards.
2. Do NOT generate "tooltip", "modal", "overlay", "popup", or "expanded" states unless
   explicitly in the source HTML.
3. Do NOT add decorative elements (blobs, shapes, gradients) unless they appear in the source.
4. ALWAYS render ALL children — never truncate or drop children from a list.
   If there are 4 cards, all 4 must appear in the output JSON.
5. NEVER place a sibling section as a child of another section. Keep the tree flat where the
   HTML is flat.
6. AFTER A GRID BLOCK: If the HTML has sections that come AFTER a grid (e.g. a "Full Stack"
   card below a 2×2 product grid), those sections MUST be separate children of the PAGE's
   vertical layout frame — NOT nested inside the grid container, NOT given
   "layoutPositioning": "ABSOLUTE", NOT given any x/y offset. They are plain siblings.
   The page's VERTICAL layoutMode will stack them naturally below the grid.
   WRONG:
     { "name": "Card Grid", "layoutMode": "NONE", "children": [
         card1, card2, card3, card4,
         { "name": "Full Stack", "layoutPositioning": "ABSOLUTE" }  ← WRONG
     ]}
   RIGHT:
     { "name": "Page", "layoutMode": "VERTICAL", "children": [
         { "name": "Card Grid", "layoutMode": "NONE", "children": [card1,card2,card3,card4] },
         { "name": "Full Stack Section", "layoutMode": "VERTICAL", ... }  ← CORRECT sibling
     ]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHILD HEIGHT CALCULATION — MANDATORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For every VERTICAL auto-layout frame, you MUST calculate the height manually:
  height = paddingTop + paddingBottom + sum(each child's height) + itemSpacing × (childCount - 1)

For TEXT children with fixed width:
  - Single line: height ≈ fontSize × 1.3 (round up)
  - Two lines:   height ≈ fontSize × 1.3 × 2 + any lineHeight offset
  - Always add a few px buffer (4–8px) for text wrapping uncertainty

Example card with title + 2-line description:
  paddingTop=24, paddingBottom=24, itemSpacing=12
  title height = 18 × 1.3 = ~24px
  body height (2 lines at 14px) = 14 × 1.3 × 2 = ~37px
  card height = 24 + 24 + 24 + 12 + 37 = 121px → round to 130px (add buffer)

NEVER set height=0 or omit height on a frame with children.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMAGE FILLS — CRITICAL RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEVER output fills with type "IMAGE" and a "src" key directly in the fills array of a
FRAME, RECTANGLE, or any container node. Figma requires an "imageHash" (fetched server-side),
not a raw URL. Doing so causes a fatal crash: "Required value missing at [0].imageHash".

WRONG (crashes):
  "fills": [{"type":"IMAGE","src":"https://..."}]

RIGHT — use a separate IMAGE node with src at the node level:
  {"type":"IMAGE","name":"Hero","width":400,"height":240,"src":"https://...","scaleMode":"FILL"}

Or use a solid/gradient fill as a placeholder when the image is decorative:
  "fills": [{"type":"SOLID","color":{"r":0.2,"g":0.2,"b":0.2}}]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPLEX UI PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PATTERN 1 — RANGE SLIDER (e.g. Temperature, Top P):
Use a FRAME (track) containing a RECTANGLE (filled portion) and an ELLIPSE (thumb).
{
  "type": "FRAME", "name": "Slider - Temperature",
  "layoutMode": "NONE",
  "width": 180, "height": 16,
  "fills": [],
  "children": [
    {
      "type": "RECTANGLE", "name": "Track",
      "x": 0, "y": 5, "width": 180, "height": 4,
      "cornerRadius": 2,
      "fill": "#333333"
    },
    {
      "type": "RECTANGLE", "name": "Fill",
      "x": 0, "y": 5, "width": 90, "height": 4,
      "cornerRadius": 2,
      "fill": "#76B900"
    },
    {
      "type": "ELLIPSE", "name": "Thumb",
      "x": 82, "y": 1, "width": 14, "height": 14,
      "fill": "#76B900"
    }
  ]
}

PATTERN 2 — SPLIT PANEL LAYOUT (sidebar + main content, side by side):
Use a HORIZONTAL auto-layout frame. Sidebar has fixed width, content panel takes remaining space.
{
  "type": "FRAME", "name": "Split Panel",
  "layoutMode": "HORIZONTAL", "width": 900, "height": 520,
  "itemSpacing": 0, "fills": [{"type":"SOLID","color":{"r":0.08,"g":0.08,"b":0.08}}],
  "children": [
    {
      "type": "FRAME", "name": "Sidebar",
      "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
      "width": 200, "height": 520,
      "paddingTop": 24, "paddingBottom": 24, "paddingLeft": 16, "paddingRight": 16,
      "itemSpacing": 20,
      "fills": [{"type":"SOLID","color":{"r":0.1,"g":0.1,"b":0.1}}],
      "strokes": [{"type":"SOLID","color":{"r":0.2,"g":0.2,"b":0.2}}],
      "strokeWeight": 1, "strokeAlign": "INSIDE",
      "strokeTopWeight": 0, "strokeLeftWeight": 0, "strokeBottomWeight": 0,
      "strokeRightWeight": 1,
      "children": [
        { slider node for Temperature },
        { slider node for Top P },
        { slider node for Max Tokens }
      ]
    },
    {
      "type": "FRAME", "name": "Main Content",
      "layoutMode": "VERTICAL",
      "width": 700, "height": 520,
      "fills": [],
      "children": [...]
    }
  ]
}

PATTERN 3 — TERMINAL / CODE BLOCK / CHAT OUTPUT:
Dark background frame, monospace text, optional scrollable content area.
{
  "type": "FRAME", "name": "Terminal Output",
  "layoutMode": "VERTICAL", "primaryAxisAlignItems": "MIN",
  "width": 680, "height": 360,
  "paddingTop": 16, "paddingBottom": 16, "paddingLeft": 16, "paddingRight": 16,
  "itemSpacing": 8,
  "cornerRadius": 4,
  "fills": [{"type":"SOLID","color":{"r":0.07,"g":0.09,"b":0.07}}],
  "clipsContent": true,
  "children": [
    {"type":"TEXT","characters":"> SYSTEM: Connection established to Blackwell Cluster H100_A800.","fontSize":13,"fontFamily":"Roboto Mono","fontStyle":"Regular","color":"#76B900","width":648,"textAutoResize":"HEIGHT"},
    {"type":"TEXT","characters":"> Hello. How can I assist with your development today?","fontSize":13,"fontFamily":"Roboto Mono","fontStyle":"Regular","color":"#76B900","width":648,"textAutoResize":"HEIGHT"},
    {"type":"TEXT","characters":"Explain the benefits of FP8 quantization in modern LLMs.","fontSize":13,"fontFamily":"Roboto Mono","fontStyle":"Regular","color":"#888888","textAlignHorizontal":"RIGHT","width":648,"textAutoResize":"HEIGHT"},
    {"type":"TEXT","characters":"FP8 (8-bit floating point) provides a significant leap in throughput by reducing memory bandwidth requirements while maintaining model accuracy. On H100 GPUs, the Transformer Engine dynamically manages precision to maximize performance...","fontSize":13,"fontFamily":"Roboto Mono","fontStyle":"Regular","color":"#CCCCCC","width":648,"textAutoResize":"HEIGHT"}
  ]
}

PATTERN 4 — DROPDOWN / SELECT with chevron:
{
  "type": "FRAME", "name": "Model Selector",
  "layoutMode": "HORIZONTAL",
  "primaryAxisAlignItems": "SPACE_BETWEEN", "counterAxisAlignItems": "CENTER",
  "width": 160, "height": 36,
  "paddingLeft": 12, "paddingRight": 10,
  "cornerRadius": 4,
  "fills": [{"type":"SOLID","color":{"r":0.12,"g":0.12,"b":0.12}}],
  "strokes": [{"type":"SOLID","color":{"r":0.25,"g":0.25,"b":0.25}}],
  "strokeWeight": 1, "strokeAlign": "INSIDE",
  "children": [
    {"type":"TEXT","characters":"Llama-3-70B","fontSize":13,"color":"#EEEEEE"},
    {"type":"TEXT","characters":"▾","fontSize":12,"color":"#888888"}
  ]
}

PATTERN 5 — STATUS INDICATOR DOT (online / connected):
{
  "type": "FRAME", "name": "Status",
  "layoutMode": "HORIZONTAL", "counterAxisAlignItems": "CENTER", "itemSpacing": 6,
  "height": 20, "fills": [],
  "children": [
    {"type":"ELLIPSE","name":"Dot","width":8,"height":8,"fill":"#76B900",
     "glow":{"color":"#76B900","opacity":0.6,"radius":6}},
    {"type":"TEXT","characters":"NVIDIA NIM","fontSize":12,"fontStyle":"Bold","color":"#EEEEEE"}
  ]
}

PATTERN 6 — TOOLBAR / TOP BAR with breadcrumb:
{
  "type": "FRAME", "name": "Toolbar",
  "layoutMode": "HORIZONTAL",
  "primaryAxisAlignItems": "SPACE_BETWEEN", "counterAxisAlignItems": "CENTER",
  "width": 900, "height": 48,
  "paddingLeft": 16, "paddingRight": 16,
  "fills": [{"type":"SOLID","color":{"r":0.1,"g":0.1,"b":0.1}}],
  "strokes": [{"type":"SOLID","color":{"r":0.2,"g":0.2,"b":0.2}}],
  "strokeWeight": 1, "strokeAlign": "INSIDE",
  "strokeTopWeight": 0, "strokeLeftWeight": 0, "strokeRightWeight": 0,
  "strokeBottomWeight": 1,
  "children": [
    {
      "type": "FRAME", "name": "Breadcrumb",
      "layoutMode": "HORIZONTAL", "counterAxisAlignItems": "CENTER",
      "itemSpacing": 4, "fills": [],
      "children": [
        {"type":"TEXT","characters":"NVIDIA NIM","fontSize":13,"fontStyle":"Bold","color":"#EEEEEE"},
        {"type":"TEXT","characters":"/","fontSize":13,"color":"#555555"},
        {"type":"TEXT","characters":"Llama-3-70B-Instruct","fontSize":13,"color":"#AAAAAA"}
      ]
    },
    { dropdown node }
  ]
}
"""

async def _process_single_screen(title: str, html: str):
    user_prompt = f"Target Screen: {title}\n\nHTML/Design to convert to Figma JSON:\n{html}"
    raw = await generate_text(
        contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
        system_instruction=FIGMA_BRIDGE_SYSTEM_PROMPT,
        temperature=0.1,
    )
    cleaned = re.sub(r"^```[\w]*\n?", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```$", "", cleaned.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)

@router.post("/generate-schema")
async def generate_figma_schema(request: FigmaSchemaRequest):
    try:
        session_id = str(uuid.uuid4())
        connected = len(manager.active)
        results = []

        if request.screens is not None:
            for s in request.screens:
                title = s.get("title", "Untitled")
                html = s.get("html", "")
                data = await _process_single_screen(title, html)

                if connected > 0:
                    await manager.broadcast({ "type": "RENDER", "schema": data, "label": title })
                    print(f"[WS] Broadcasted screen '{title}'")

                results.append({"title": title, "schema": data})

            return {
                "success": True,
                "session_id": session_id,
                "delivered": connected > 0,
                "recipients": connected,
                "count": len(results)
            }
        else:
            if not request.html or not request.title:
                raise HTTPException(status_code=400, detail="HTML and Title required for single screen export")

            title = request.title or "Untitled"
            html = request.html or ""
            data = await _process_single_screen(title, html)

            if connected > 0:
                await manager.broadcast({ "type": "RENDER", "schema": data, "label": request.title })
                print(f"[WS] Pushed '{request.title}' to {connected} plugin(s)")

            return {
                "success":    True,
                "session_id": session_id,
                "schema":     data,
                "delivered":  connected > 0,
                "recipients": connected,
            }

    except Exception as exc:
        print(f"[Figma Export] Error: {exc}")
        return {"success": False, "error": str(exc)}