// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title IERC20
/// @notice Minimal ERC-20 interface used by the test token.
interface IERC20 {
    /// @notice Emitted when tokens are transferred between accounts.
    event Transfer(address indexed from, address indexed to, uint256 value);

    /// @notice Emitted when an allowance is set via `approve`.
    event Approval(address indexed owner, address indexed spender, uint256 value);

    /// @notice Returns the total token supply.
    function totalSupply() external view returns (uint256);

    /// @notice Returns the token balance of `account`.
    function balanceOf(address account) external view returns (uint256);

    /// @notice Transfers `amount` tokens to `to`.
    function transfer(address to, uint256 amount) external returns (bool);

    /// @notice Returns the remaining allowance that `spender` has over `owner`'s tokens.
    function allowance(address owner, address spender) external view returns (uint256);

    /// @notice Sets `amount` as the allowance of `spender` over the caller's tokens.
    function approve(address spender, uint256 amount) external returns (bool);

    /// @notice Moves `amount` tokens from `from` to `to` using the allowance mechanism.
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}
