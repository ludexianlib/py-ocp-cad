from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone


def main():
    box = BRepPrimAPI_MakeBox(40.0, 30.0, 10.0).Shape()

    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(box, properties)
    print("volume: ", round(properties.Mass(), 6))

    writer = STEPControl_Writer()
    if writer.Transfer(box, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError("transfer error")
    if writer.Write("box.step") != IFSelect_RetDone:
        raise RuntimeError("export error")
    print("success")


if __name__ == "__main__":
    main()