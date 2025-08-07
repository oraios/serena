// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "test_repo",
    products: [
        .library(
            name: "test_repo",
            targets: ["test_repo"]),
    ],
    targets: [
        .target(
            name: "test_repo",
            dependencies: []),
    ]
)