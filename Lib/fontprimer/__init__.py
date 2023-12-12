import os
import copy
import babelfont
import logging
import re
import sys
import yaml
from tempfile import NamedTemporaryFile

from strictyaml import YAML

from gftools.util.styles import RIBBI_STYLE_NAMES
from gftools.builder.recipeproviders.googlefonts import GFBuilder, DEFAULTS
from gftools.builder.recipeproviders import boolify
from gftools.builder.schema import stat_schema


log = logging.getLogger("fontprimer")

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
        if "stat" in self.config:
            self.statfile = NamedTemporaryFile(mode="w", delete=False)
            self.config["stat"].revalidate(stat_schema)
            yaml.dump(self.config["stat"].data, self.statfile)
            self.statfile.close()
        else:
            self.statfile = None
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
            self.recipe[self.apex_vf_path(guideline)] = self.variable_steps(
                guideline
            ) + [{"operation": "hbsubset"}]

        # Build color apex
        if boolify(self.config.get("buildColorVariable", True)):
            self.build_color_guidelines()

        # Build variant VFs
        for variant in self.config.get("variants", []):
            for guideline in self.guidelines:
                self.build_variant_vf(variant.data, guideline)

    def build_STAT(self):
        if self.statfile:
            args = {"args": "--src " + self.statfile.name}
        else:
            args = {}
        return {"operation": "buildStat", **args}

    def build_color_guidelines(self):
        ordinary_vf = self.apex_vf_path()
        color_vf = self.apex_vf_path(color=True)
        sourcepath = self.sources[0].path
        guidelines_path = sourcepath.replace(".glyphs", ".colr-guidelines.glyphs")
        variant = {"name": "Color", "alias": "COLR"}
        new_axes = [ax.tag for ax in self.first_source.axes if ax.tag] + ["GDLO"]
        new_family_name = self.abbreviate_family_name(variant, False)
        vfname = new_family_name.replace(" ", "") + f"[{','.join(new_axes)}].ttf"
        target = os.path.join(self.config["vfDir"], vfname)
        self.recipe[target] = [
            {"source": sourcepath},
            {
                "operation": "exec",
                "exe": sys.executable + " -m fontprimer.guidelines",
                "args": "--color -o %s %s" % (guidelines_path, sourcepath),
            },
            {"source": guidelines_path},
            {
                "operation": "buildVariable",
                "fontmake_args": self.fontmake_args(),
            },
            self.build_STAT(),
            {"operation": "rename", "name": new_family_name},
            {
                "postprocess": "exec",
                "exe": sys.executable + " -m fontprimer.colrguidelines",
                "args": f"-o {target} {target}",
            },
        ]

    def build_variant_vf(self, variant, guideline=False):
        assert not isinstance(variant, YAML)
        new_family_name = self.abbreviate_family_name(variant, guideline)
        # Check in the steps to see if we are pinning any axes
        pins = pinned_axes(variant)
        new_axes = [ax.tag for ax in self.first_source.axes if ax.tag not in pins]
        italic_part = ""
        if variant.get("italic"):
            italic_part = "-Italic"
            pass
        vfname = new_family_name.replace(" ", "") + italic_part + f"[{','.join(new_axes)}].ttf"
        recipe = self.recipe[os.path.join(self.config["vfDir"], vfname)] = (
            self.variable_steps(guideline)
            + copy.deepcopy(variant.get("steps", []))
        )

        recipe.extend([
                {"operation": "rename", "name": new_family_name},
                {"operation": "fix", "args": "--include-source-fixes"},
                {"operation": "hbsubset"},
            ]
        )

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
            variant = {"name": "-Color", "alias": "COLR"}
        family_name = self.abbreviate_family_name(
            variant=variant, guidelines=guidelines
        )
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
                    "args": self.fontmake_args(),
                },
                {"operation": "fix", "args": "--include-source-fixes"},
                self.build_STAT(),
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

        custom_instances = [x.name.get_default() for x in self.first_source.instances if x not in RIBBI_STYLE_NAMES]
        if variant:
            if variant.get("italic"):
                custom_instances = [x for x in custom_instances if "Italic" not in x]
            else:
                custom_instances = [x for x in custom_instances if "Italic" in x]
        longest_instance_name = max(custom_instances, key=len)

        elements.append(longest_instance_name)

        if len(" ".join(elements)) > 32:
            # Try to shorten
            if guidelines:
                elements[2] = "Guide"
            if len(" ".join(elements)) > 32 and variant and variant.get("alias"):
                elements[1] = variant.get("alias")
            if len(" ".join(elements)) > 32 and "shortFamilyName" in self.config:
                elements[0] = str(self.config["shortFamilyName"])
            if len(" ".join(elements)) > 32:
                log.warn(
                    "Font name '%s' too long; provide shortFamilyName and variant aliases"
                    % " ".join(elements)
                )
        elements.pop()  # Remove instance name
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
        if "Italic" in filename and (variant and not variant.get("italic")):
            return
        if "Italic" not in filename and (variant and variant.get("italic")):
            return

        self.recipe[target] = self.variable_steps(guidelines)
        if variant:
            self.recipe[target].extend(copy.deepcopy(variant.get("steps")))
        self.recipe[target].extend(
            [
                {"operation": "rename", "name": new_family_name},
                {
                    "operation": "subspace",
                    "axes": location,
                    "args": "--update-name-table",
                },
                {"operation": "hbsubset"},
                {"operation": "fix", "args": "--include-source-fixes"},
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
