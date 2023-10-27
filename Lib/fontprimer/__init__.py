import os
import copy
import babelfont
import re
import sys

from strictyaml import YAML

from gftools.builder.recipeproviders.googlefonts import GFBuilder, DEFAULTS
from gftools.builder.recipeproviders import boolify


def pinned_axes(variant):
    pins = set()
    for step in variant["steps"]:
        if "operation" not in step:
            continue
        if step["operation"] == "subspace":
            for axis in step["axes"].split():
                axis, stops = axis.split("=")
                if ":" not in stops:
                    pins.add(axis)
    return pins


class FontPrimer(GFBuilder):
    def write_recipe(self):
        self.recipe = {}
        self.config = {**DEFAULTS, **self.config}
        self.first_source = babelfont.load(self.sources[0].path)
        self.build_all_variables()
        self.build_all_statics()
        return self.recipe

    @property
    def guidelines(self):
        if boolify(self.config.get("doGuidelines")):
            return [False, True]
        return [False]

    def build_all_variables(self):
        if not boolify(self.config.get("buildVariable", True)):
            return

        # Build apex VF
        for guideline in self.guidelines:
            self.recipe[self.apex_vf_path(guideline)] = self.variable_steps(guideline)

        # Build color apex
        if boolify(self.config.get("buildColorVariable", True)):
            self.build_variant_vf(self.color_guidelines(), False)

        # Build variant VFs
        for variant in self.config.get("variants", []):
            for guideline in self.guidelines:
                self.build_variant_vf(variant.data, guideline)

    def color_guidelines(self):
        ordinary_vf = self.apex_vf_path()
        color_vf = self.apex_vf_path(color=True)
        sourcepath = self.sources[0].path
        guidelines_path = sourcepath.replace(".glyphs", ".colr-guidelines.glyphs")
        return {
            "name": "Color",
            "alias": "COLR",
            "steps": [
                {
                    "operation": "exec",
                    "exe": sys.executable + " -m fontprimer.guidelines",
                    "args": "--color -o %s %s" % (guidelines_path, sourcepath),
                },
                {
                    "source": guidelines_path
                },
                {
                    "operation": "exec",
                    "exe": sys.executable + " -m fontprimer.colrguidelines",
                    "args": f"-o {color_vf} {ordinary_vf}"
                }
            ],
        }

    def build_variant_vf(self, variant, guideline=False):
        assert not isinstance(variant, YAML)
        new_family_name = self.abbreviate_family_name(variant, guideline)
        # Check in the steps to see if we are pinning any axes
        pins = pinned_axes(variant)
        new_axes = [ax.tag for ax in self.first_source.axes if ax.tag not in pins]
        vfname = new_family_name.replace(" ", "") + f"[{','.join(new_axes)}].ttf"
        self.recipe[os.path.join(self.config["vfDir"], vfname)] = self.variable_steps(
            guideline
        ) + copy.deepcopy(variant.get("steps", [])) +  [
                {"operation": "rename", "name": new_family_name},
        ]

    def build_all_statics(self):
        if not boolify(self.config.get("buildStatic", True)):
            return
        source = self.sources[0]

        # Build apex statics
        for guideline in self.guidelines:
            for instance in self.first_source.instances:
                self.build_a_static(
                    source, instance, guidelines=guideline, output="ttf"
                )

        # Build variant statics
        for definition in self.config.get("variants", []):
            variantname = definition["name"]
            for guideline in self.guidelines:
                for instance in self.first_source.instances:
                    self.build_a_static(
                        source,
                        instance,
                        add_name=variantname,
                        variant=definition.data,
                        guidelines=guideline,
                        output="ttf",
                    )

    def apex_vf_path(self, guidelines=False, color=False):
        if len(self.sources) > 1:
            raise ValueError("Only one source supported")
        source = self.sources[0]
        if (
            (source.is_glyphs and len(source.gsfont.masters) < 2)
            or source.is_ufo
            or (source.is_designspace and len(source.designspace.sources) < 2)
        ):
            return None
        tags = [ax.tag for ax in self.first_source.axes]
        axis_tags = ",".join(sorted(tags))
        variant = None
        if color:
            variant = { "name": "-Color", "alias": "COLR"}
        family_name = self.abbreviate_family_name(variant=variant, guidelines=guidelines)
        sourcebase = family_name.replace(" ", "")
        return os.path.join(self.config["vfDir"], f"{sourcebase}[{axis_tags}].ttf")

    def fontmake_args(self):
        return super().fontmake_args() + " --no-production-names"

    def variable_steps(self, guidelines=False):
        sourcepath = self.sources[0].path
        guidelines_steps = []
        if guidelines:
            guidelines_path = sourcepath.replace(".glyphs", ".guidelines.glyphs")
            guidelines_steps = [
                {
                    "operation": "exec",
                    "exe": sys.executable + " -m fontprimer.guidelines",
                    "args": "-o %s %s" % (guidelines_path, sourcepath),
                },
                {"source": guidelines_path},
            ]
        return (
            [{"source": sourcepath}]
            + guidelines_steps
            + [
                {
                    "operation": "buildVariable",
                    "fontmake_args": self.fontmake_args(),
                },
                {"operation": "buildStat"},
            ]
        )

    def abbreviate_family_name(self, variant=None, guidelines=False):
        elements = [
            self.first_source.names.familyName.get_default(),
        ]
        if variant:
            elements.append(variant["name"])
        if guidelines:
            elements.append("Guidelines")

        if len(" ".join(elements)) > 28:
            # Try to shorten
            if guidelines:
                elements[2] = "Guide"
            if len(" ".join(elements)) > 28 and variant and variant.get("alias"):
                elements[1] = variant.get("alias")
            if len(" ".join(elements)) > 28 and "shortFamilyName" in self.config:
                elements[0] = str(self.config["shortFamilyName"])
            if len(" ".join(elements)) > 28:
                raise ValueError(
                    "Family name '%s' too long; provide shortFamilyName and variant aliases"
                    % " ".join(elements)
                )
        return " ".join(elements)

    def build_a_static(
        self,
        source,
        instance,
        add_name="",
        variant=None,
        guidelines=False,
        output="ttf",
    ):
        method = "cut_instances"
        if output == "ttf":
            outdir = self.config["ttDir"]
        else:
            outdir = self.config["otDir"]
        new_family_name = self.abbreviate_family_name(variant, guidelines)

        filename = (
            new_family_name.replace(" ", "")
            + "-"
            + instance.styleName.get_default().replace(" ", "")
        )
        if "staticTemplate" in self.config:
            outdir = self.static_template(variant, guidelines, output)
        target = os.path.join(outdir, f"{filename}.{output}")
        # Or maybe backward...
        instance_location = self.first_source.map_forward(instance.location)
        if variant is not None:
            pins = pinned_axes(variant)
        else:
            pins = []
        location = " ".join(
            [
                f"{ax}={value}"
                for ax, value in instance_location.items()
                if ax not in pins
            ]
        )
        if not location:
            return
        # Special case for Playwright, may bite us
        if "Italic" in filename and "slnt" not in location and "ital" not in location:
            return
        self.recipe[target] = self.variable_steps(guidelines)
        if variant:
            self.recipe[target].extend(copy.deepcopy(variant.get("steps")))
        self.recipe[target].append(
            {
                "operation": "subspace",
                "axes": location,
                # "other_args": "--update-name-table"
            },
        )
        self.recipe[target].extend(
            [
                {"operation": "rename", "name": new_family_name},
                {"operation": "fix", "fixargs": "--include-source-fixes"},
            ]
        )

    def static_template(self, variant, guidelines, output_format):
        template = self.config["staticTemplate"]
        def replacer(matchobj):
            var = matchobj[1]
            if var == "variant":
                if variant:
                    return variant["name"]
                return ""
            if var == "format":
                return output_format
            if var == "guidelines":
                if guidelines:
                    return "Guidelines"
                else:
                    return ""
            if var in self.config:
                return self.config[var]
            raise ValueError("Couldn't understand template variable {%%%s}" % var)
        replaced = re.sub(r"%{([^}]+)}", replacer, template)
        return replaced
