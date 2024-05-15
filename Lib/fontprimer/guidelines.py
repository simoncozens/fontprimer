from glyphsLib.classes import GSLINE, GSFont, GSNode, GSPath, GSGlyph, GSLayer


# from https://github.com/mekkablue/Glyphs-Scripts/blob/a4421210dd17305e3205b7ca998cab579b778bf6/Paths/Fill%20Up%20with%20Rectangles.py
def drawRect(myBottomLeft, myTopRight):
    myRect = GSPath()
    myCoordinates = [
        [myBottomLeft[0], myBottomLeft[1]],
        [myTopRight[0], myBottomLeft[1]],
        [myTopRight[0], myTopRight[1]],
        [myBottomLeft[0], myTopRight[1]],
    ]

    for thisPoint in myCoordinates:
        newNode = GSNode((thisPoint[0], thisPoint[1]), GSLINE)
        myRect.nodes.append(newNode)

    myRect.closed = True
    return myRect


def decomposed_paths(layer):
    newpaths = [l.clone() for l in layer.paths]
    for component in layer.components:
        transform = component.transform
        to_append = decomposed_paths(component.layer)
        for path in to_append:
            path.applyTransform(transform)
        newpaths += to_append
    return newpaths


def decompose_all_layers(font):
    for glyph in font.glyphs:
        for layer in glyph.layers:
            layer.shapes = list(layer.paths) + decomposed_paths(layer)


def add_guidelines(font, args):
    for glyph in font.glyphs:
        if glyph.name.startswith("_"):
            continue
        if not glyph.export:
            continue
        # Skip combining marks
        for layer in glyph.layers:
            # If this has any components which don't start in "_part", skip it
            if layer.components and not all(
                component.name.startswith("_part") for component in layer.components
            ):
                continue
            # Skip anything with underscore anchors
            if any(anchor.name.startswith("_") for anchor in layer.anchors):
                continue
            master = layer.master
            heightsAndThicknesses = [
                (master.descender, args.default_thickness),
                (0 + args.thicker_thickness / 2, args.thicker_thickness),
                (master.xHeight, args.default_thickness),
                (master.ascender, args.default_thickness),
            ]

            for height, thickness in heightsAndThicknesses:
                bottomLeft = (-args.overlap, height - thickness / 2)
                topRight = (layer.width + args.overlap, height + thickness / 2)
                layerRect = drawRect(bottomLeft, topRight)
                layer.shapes.append(layerRect)


def add_guideline_glyph(font, thickness):
    if "_guide" in font.glyphs:
        return
    font.glyphs.append(GSGlyph("_guide"))
    for master in font.masters:
        layer = GSLayer()
        layer.associatedMasterId = master.id
        layer.layerId = master.id
        layer.width = 1000
        layer.shapes = [GSPath()]
        layer.shapes[0].nodes = [
            GSNode((0, 0), GSLINE),
            GSNode((1000, 0), GSLINE),
            GSNode((1000, thickness), GSLINE),
            GSNode((0, thickness), GSLINE),
        ]
        font.glyphs["_guide"].layers.append(layer)
    pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("font", help="Glyphs file", metavar="GLYPHS")
    parser.add_argument(
        "--color",
        action="store_true",
        help="Output a single stroke for color processing",
    )
    parser.add_argument("--output", "-o", help="Output file", metavar="GLYPHS")
    parser.add_argument(
        "--overlap", help="Overlap of the guidelines", type=int, default=10
    )
    parser.add_argument(
        "--default-thickness", help="Default guideline thickness", type=int, default=16
    )
    parser.add_argument(
        "--thicker-thickness", help="Thicker guideline thickness", type=int, default=32
    )
    args = parser.parse_args()

    if not args.output:
        args.output = args.font
    font = GSFont(args.font)
    if args.color:
        add_guideline_glyph(font, args.default_thickness)
    else:
        decompose_all_layers(font)
        add_guidelines(font, args)
    print("Saving on " + args.output)
    font.save(args.output)
