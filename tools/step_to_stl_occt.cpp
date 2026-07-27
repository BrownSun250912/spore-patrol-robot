#include <BRepMesh_IncrementalMesh.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <STEPControl_Reader.hxx>
#include <StlAPI_Writer.hxx>
#include <TopoDS_Shape.hxx>

#include <cstdlib>
#include <iostream>

int main(int argc, char **argv)
{
  if (argc < 3 || argc > 4) {
    std::cerr << "Usage: step_to_stl_occt INPUT.stp OUTPUT.stl [linear_deflection_mm]\n";
    return 2;
  }

  const double deflection = argc == 4 ? std::atof(argv[3]) : 1.0;
  if (deflection <= 0.0) {
    std::cerr << "linear_deflection_mm must be positive\n";
    return 2;
  }

  STEPControl_Reader reader;
  const IFSelect_ReturnStatus status = reader.ReadFile(argv[1]);
  if (status != IFSelect_RetDone) {
    std::cerr << "Failed to read STEP file\n";
    return 1;
  }

  const Standard_Integer transferred = reader.TransferRoots();
  if (transferred <= 0) {
    std::cerr << "STEP file contained no transferable roots\n";
    return 1;
  }

  const TopoDS_Shape shape = reader.OneShape();
  if (shape.IsNull()) {
    std::cerr << "Transferred STEP shape is empty\n";
    return 1;
  }

  BRepMesh_IncrementalMesh mesher(shape, deflection, Standard_False, 0.35, Standard_True);
  mesher.Perform();
  if (!mesher.IsDone()) {
    std::cerr << "OpenCASCADE surface meshing did not complete\n";
    return 1;
  }

  StlAPI_Writer writer;
  writer.ASCIIMode() = Standard_False;
  if (!writer.Write(shape, argv[2])) {
    std::cerr << "Failed to write STL file\n";
    return 1;
  }

  std::cout << "Converted " << transferred << " STEP root(s) to " << argv[2]
            << " with " << deflection << " mm deflection\n";
  return 0;
}
