import { Route } from "react-router-dom";
import { ShadowPage } from "./pages/ShadowPage";

{
  const Route = (props: object) => <div {...props} />;
  const shadowed = <Route path="/shadow" Component={ShadowPage} />;
  void shadowed;
}
