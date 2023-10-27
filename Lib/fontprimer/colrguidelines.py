from fontTools.ttLib import TTFont
from paintcompiler import add_axes, compile_paints
from fontTools.pens.boundsPen import BoundsPen


def paints():
    # All variables here are magic
    glyphset = font.getGlyphSet()
    xHeight = font["OS/2"].sxHeight
    capheight = font["OS/2"].sCapHeight
    ascender = font["OS/2"].sTypoAscender
    descender = font["OS/2"].sTypoDescender
    guideline = PaintGlyph(
                        "_guide",
                        PaintSolid(
                            "#0000FFFF",
                            {
                                (("GDLO", 0),): 0.0,
                                (("GDLO", 1),): 1.0,
                            }
                        ),
                    )
    for glyphname in font.getGlyphOrder():
        # For now we will assume advance width is static, but we will need to
        # consider variations later
        width = font["hmtx"][glyphname][0] + 200
        scale = width / 1000
       
        baselinematrix = (scale, 0, 0, 2, -100, -8)
        xheightmatrix = (scale, 0, 0, 1, -100, xHeight-8)
        capheightmatrix = (scale, 0, 0, 1, -100, capheight-8)
        ascendermatrix = (scale, 0, 0, 2, -100, ascender-16)
        descendermatrix = (scale, 0, 0, 2, -100, descender-16)
        glyphs[glyphname] = PaintColrLayers(
            [
                PaintTransform(baselinematrix, guideline),
                PaintTransform(xheightmatrix, guideline),
                PaintTransform(capheightmatrix, guideline),
                PaintTransform(ascendermatrix, guideline),
                PaintTransform(descendermatrix, guideline),
                PaintGlyph(glyphname, PaintSolid("foreground")),
            ]
        )


def add_guidelines(font):
    # Add GDLO axis
    add_axes(font,
        [
            "GDLO:0:1.0:1.0:Guideline Opacity",
        ]
    )
    compile_paints(font, paints.__code__)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("font", help="TTF file", metavar="TTF")
    parser.add_argument("--output", "-o", help="Output file", metavar="TTF")
    args = parser.parse_args()

    if not args.output:
        args.output = args.font
    font = TTFont(args.font)
    add_guidelines(font)
    print("Saving on " + args.output)
    font.save(args.output)
