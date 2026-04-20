import Lake
open Lake DSL

package «test_repo» where
  leanOptions := #[⟨`autoImplicit, false⟩]

@[default_target]
lean_lib «Main» where
  roots := #[`Main, `Helper]
