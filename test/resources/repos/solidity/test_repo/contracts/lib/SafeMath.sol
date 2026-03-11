// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title SafeMath
/// @notice Arithmetic helpers with overflow checks (illustrative — 0.8+ reverts natively).
library SafeMath {
    /// @notice Returns the sum of `a` and `b`, reverting on overflow.
    function add(uint256 a, uint256 b) internal pure returns (uint256) {
        return a + b;
    }

    /// @notice Returns `a` minus `b`, reverting on underflow.
    function sub(uint256 a, uint256 b) internal pure returns (uint256) {
        require(b <= a, "SafeMath: subtraction underflow");
        return a - b;
    }

    /// @notice Returns the product of `a` and `b`, reverting on overflow.
    function mul(uint256 a, uint256 b) internal pure returns (uint256) {
        if (a == 0) return 0;
        return a * b;
    }

    /// @notice Returns the integer division of `a` by `b`, reverting on division by zero.
    function div(uint256 a, uint256 b) internal pure returns (uint256) {
        require(b > 0, "SafeMath: division by zero");
        return a / b;
    }
}
