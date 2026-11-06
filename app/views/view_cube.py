"""Native OCCT navigation cube; all methods run on the rendering thread."""

import sys

from OCP.AIS import AIS_Point, AIS_ViewCube, AIS_ViewCubeOwner
from OCP.Aspect import Aspect_TypeOfMarker, Aspect_TypeOfTriedronPosition
from OCP.collections import Vec2_int
from OCP.Geom import Geom_CartesianPoint
from OCP.Graphic3d import Graphic3d_AlphaMode, Graphic3d_TypeOfShadingModel
from OCP.Graphic3d import Graphic3d_TransformPers, Graphic3d_TransModeFlags
from OCP.Graphic3d import Graphic3d_ZLayerId_Topmost, Graphic3d_ZLayerId_TopOSD
from OCP.Prs3d import Prs3d_PointAspect
from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TypeOfColor
from OCP.TCollection import TCollection_AsciiString
from OCP.V3d import V3d_TypeOfOrientation
from OCP.gp import gp_Pnt


class ViewCube:
    def __init__(self, context, view, pixel_ratio):
        self._context = context
        self._view = view
        self._pixel_ratio = None
        self._dot_corner = None
        self._dot_visible = False
        self.cube = AIS_ViewCube()
        self.cube.SetDrawAxes(False)
        self.cube.SetDrawEdges(True)
        self.cube.SetDrawVertices(True)
        self.cube.SetRoundRadius(0.18)
        self.cube.SetDuration(0.28)
        self.cube.SetFixedAnimationLoop(False)
        self.cube.SetAutoStartAnimation(False)
        self.cube.SetFitSelected(False)
        self.cube.SetInfiniteState(True)
        self.cube.SetZLayer(Graphic3d_ZLayerId_Topmost)
        self.cube.ViewAnimation().SetView(view)
        self.cube.SetBoxColor(self._color(223, 216, 239))
        self.cube.SetInnerColor(self._color(223, 216, 239))
        self.cube.Attributes().ShadingAspect().Aspect().SetShadingModel(
            Graphic3d_TypeOfShadingModel.Graphic3d_TOSM_UNLIT)
        # Keep the navigation targets in the gaps, but draw them much more
        # lightly than the main faces. Transparency does not disable picking.
        for style in (self.cube.BoxEdgeStyle(), self.cube.BoxCornerStyle()):
            style.SetColor(self._color(213, 203, 234))
            style.SetTransparency(0.82)
            style.Aspect().SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TOSM_UNLIT)
        self.cube.SetTextColor(self._color(69, 58, 91))
        self.cube.DynamicHilightAttributes().SetColor(self._color(177, 159, 231))
        font = "Microsoft YaHei" if sys.platform == "win32" else "Noto Sans CJK SC"
        self.cube.SetFont(TCollection_AsciiString(font))
        labels = {
            V3d_TypeOfOrientation.V3d_Yneg: "前",
            V3d_TypeOfOrientation.V3d_Ypos: "后",
            V3d_TypeOfOrientation.V3d_Xneg: "左",
            V3d_TypeOfOrientation.V3d_Xpos: "右",
            V3d_TypeOfOrientation.V3d_Zpos: "上",
            V3d_TypeOfOrientation.V3d_Zneg: "下",
        }
        for orientation, label in labels.items():
            self.cube.SetBoxSideLabel(orientation, TCollection_AsciiString(label))
        self._center_dot = AIS_Point(Geom_CartesianPoint(gp_Pnt(0, 0, 0)))
        self._center_dot.SetInfiniteState(True)
        self._center_dot.SetZLayer(Graphic3d_ZLayerId_TopOSD)
        self.update_scale(pixel_ratio)
        context.Display(self.cube, False)

    @staticmethod
    def _color(red, green, blue):
        return Quantity_Color(red / 255, green / 255, blue / 255, Quantity_TypeOfColor.Quantity_TOC_sRGB)

    def update_scale(self, pixel_ratio):
        if self._pixel_ratio == pixel_ratio:
            return
        self._pixel_ratio = pixel_ratio
        self.cube.SetSize(50 * pixel_ratio)
        self.cube.SetRoundRadius(0.18)
        self.cube.SetBoxFacetExtension(3 * pixel_ratio)
        self.cube.SetBoxEdgeGap(0.5 * pixel_ratio)
        self.cube.SetFontHeight(12 * pixel_ratio)
        self.cube.SetTransformPersistence(Graphic3d_TransformPers(
            Graphic3d_TransModeFlags.Graphic3d_TMF_TriedronPers,
            Aspect_TypeOfTriedronPosition.Aspect_TOTP_RIGHT_UPPER,
            Vec2_int(round(64 * pixel_ratio), round(64 * pixel_ratio)),
        ))
        self._center_dot.SetTransformPersistence(self.cube.TransformPersistence())
        point = Prs3d_PointAspect(Aspect_TypeOfMarker.Aspect_TOM_POINT, self._color(115, 100, 145), pixel_ratio)
        point.Aspect().SetInteriorColor(Quantity_ColorRGBA(self._color(115, 100, 145), 0.22))
        point.Aspect().SetAlphaMode(Graphic3d_AlphaMode.Graphic3d_AlphaMode_Blend)
        self._center_dot.Attributes().SetPointAspect(point)
        self._dot_corner = None
        if self._context.IsDisplayed(self.cube):
            self._context.Redisplay(self.cube, False)

    def is_detected(self):
        return self._context.HasDetected() and isinstance(self._context.DetectedOwner(), AIS_ViewCubeOwner)

    def handle_click(self):
        if not self.is_detected():
            return False
        owner = self._context.DetectedOwner()
        self.cancel_animation()
        self.cube.StartAnimation(owner)
        return True

    def update_animation(self):
        if self.cube.HasAnimation():
            self.cube.UpdateAnimation(False)
        self._update_center_dot()
        return self.cube.HasAnimation()

    def _update_center_dot(self):
        direction = self._view.Camera().Direction().Coord()
        # With only one or two visible faces there is no three-face junction.
        visible = min(abs(value) for value in direction) > 0.12
        if not visible:
            if self._dot_visible:
                self._context.Erase(self._center_dot, False)
                self._dot_visible = False
            return
        corner = tuple(-1 if value > 0 else 1 for value in direction)
        if corner != self._dot_corner:
            half = self.cube.Size() / 2
            self._center_dot.SetComponent(Geom_CartesianPoint(gp_Pnt(*(value * half for value in corner))))
            self._dot_corner = corner
            if self._dot_visible:
                self._context.Redisplay(self._center_dot, False)
        if not self._dot_visible:
            self._context.Display(self._center_dot, 0, -1, False)
            self._dot_visible = True

    def cancel_animation(self):
        self.cube.ViewAnimation().Stop()
