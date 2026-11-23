// Vygeneruje štítky kvality do výběru streamu (resources/media/q*.png, 256x256, průhledné pozadí).
//
//     swift tools/make_badges.swift
//
// Potřebuje macOS (kreslí písmem systému přes AppKit). Hotové obrázky jsou součástí repozitáře,
// takže skript stačí pustit jen při změně vzhledu štítků.
import AppKit

let size = 256
let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
let target = root.appendingPathComponent("plugin.video.mojekino/resources/media")

func rgb(_ r: Int, _ g: Int, _ b: Int) -> NSColor {
    return NSColor(srgbRed: CGFloat(r) / 255, green: CGFloat(g) / 255, blue: CGFloat(b) / 255, alpha: 1)
}

struct Quality { let key: String; let top: String; let main: String; let color: NSColor }
struct Extra { let key: String; let text: String; let color: NSColor }

let qualities = [
    Quality(key: "2160", top: "UHD", main: "4K", color: rgb(255, 82, 112)),
    Quality(key: "1080", top: "FHD", main: "1080", color: rgb(28, 214, 164)),
    Quality(key: "720", top: "HD", main: "720", color: rgb(64, 160, 255)),
    Quality(key: "480", top: "SD", main: "480", color: rgb(160, 172, 190)),
    Quality(key: "0", top: "", main: "?", color: rgb(120, 130, 146)),
]
let extras = [
    Extra(key: "", text: "", color: .clear),
    Extra(key: "_hdr", text: "HDR", color: rgb(255, 196, 64)),
    Extra(key: "_cam", text: "CAM", color: rgb(255, 104, 80)),
    Extra(key: "_3d", text: "3D", color: rgb(204, 168, 255)),
]

/// Text vystředěný v obdélníku; písmo se zmenší, aby se vešel na šířku.
func draw(_ text: String, in rect: CGRect, size wanted: CGFloat, color: NSColor, kern: CGFloat = 0) {
    var points = wanted
    while true {
        let font = NSFont.systemFont(ofSize: points, weight: .black)
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: color, .kern: kern]
        let string = NSAttributedString(string: text, attributes: attributes)
        let width = string.size().width - kern
        if width <= rect.width || points <= 12 {
            let baseline = rect.midY - font.capHeight / 2
            string.draw(at: CGPoint(x: rect.midX - width / 2, y: baseline + font.descender))
            return
        }
        points -= 2
    }
}

func render(_ quality: Quality, _ extra: Extra) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: size, height: size)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    // výšky částí: horní nápis 62, štítek 96, spodní nápis 50, mezery 8
    let hasTop = !quality.top.isEmpty, hasExtra = !extra.text.isEmpty
    let total: CGFloat = (hasTop ? 70 : 0) + 96 + (hasExtra ? 58 : 0)
    var y = (CGFloat(size) + total) / 2            // odshora dolů
    if hasTop {
        draw(quality.top, in: CGRect(x: 8, y: y - 62, width: 240, height: 62), size: 66, color: quality.color, kern: 2)
        y -= 70
    }
    let pill = CGRect(x: 10, y: y - 96, width: 236, height: 96)
    quality.color.setFill()
    NSBezierPath(roundedRect: pill, xRadius: 22, yRadius: 22).fill()
    draw(quality.main, in: pill.insetBy(dx: 16, dy: 0), size: 76, color: rgb(12, 18, 30), kern: 1)
    y -= 96
    if hasExtra {
        draw(extra.text, in: CGRect(x: 8, y: y - 58, width: 240, height: 50), size: 52, color: extra.color, kern: 2)
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
for quality in qualities {
    for extra in extras {
        let file = target.appendingPathComponent("q\(quality.key)\(extra.key).png")
        try render(quality, extra).write(to: file)
    }
}
print("Štítky uloženy: \(target.path)")
