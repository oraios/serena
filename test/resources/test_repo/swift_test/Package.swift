// swift-tools-version:5.5
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "TestSwiftModule",
    products: [
        .library(
            name: "TestSwiftModule",
            targets: ["TestSwiftModule"]),
    ],
    dependencies: [],
    targets: [
        .target(
            name: "TestSwiftModule",
            dependencies: [],
            path: ".",
            exclude: ["Sources"],
            sources: ["Person.swift", "PersonUser.swift"]
        )
    ]
)