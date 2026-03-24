// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./interfaces/IERC20.sol";
import "./lib/SafeMath.sol";

/// @title Token
/// @notice A simple ERC-20 token implementation used as a test fixture.
contract Token is IERC20 {
    using SafeMath for uint256;

    // -------------------------------------------------------------------------
    // State variables
    // -------------------------------------------------------------------------

    string public name;
    string public symbol;
    uint8 public decimals;
    uint256 private _totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // -------------------------------------------------------------------------
    // Errors
    // -------------------------------------------------------------------------

    /// @notice Thrown when transferring to the zero address.
    error ZeroAddress();

    /// @notice Thrown when the caller's balance is insufficient.
    error InsufficientBalance(address account, uint256 required, uint256 available);

    /// @notice Thrown when the allowance is insufficient.
    error InsufficientAllowance(address spender, uint256 required, uint256 available);

    // -------------------------------------------------------------------------
    // Constructor
    // -------------------------------------------------------------------------

    /// @param _name   Human-readable token name.
    /// @param _symbol Token ticker symbol.
    /// @param supply  Initial supply minted to `msg.sender` (in whole tokens).
    constructor(string memory _name, string memory _symbol, uint256 supply) {
        name = _name;
        symbol = _symbol;
        decimals = 18;
        _mint(msg.sender, supply * 10 ** decimals);
    }

    // -------------------------------------------------------------------------
    // IERC20 view functions
    // -------------------------------------------------------------------------

    /// @inheritdoc IERC20
    function totalSupply() external view override returns (uint256) {
        return _totalSupply;
    }

    /// @inheritdoc IERC20
    function balanceOf(address account) external view override returns (uint256) {
        return _balances[account];
    }

    /// @inheritdoc IERC20
    function allowance(address owner, address spender) external view override returns (uint256) {
        return _allowances[owner][spender];
    }

    // -------------------------------------------------------------------------
    // IERC20 mutating functions
    // -------------------------------------------------------------------------

    /// @inheritdoc IERC20
    function transfer(address to, uint256 amount) external override returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    /// @inheritdoc IERC20
    function approve(address spender, uint256 amount) external override returns (bool) {
        _approve(msg.sender, spender, amount);
        return true;
    }

    /// @inheritdoc IERC20
    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        if (currentAllowance < amount) {
            revert InsufficientAllowance(msg.sender, amount, currentAllowance);
        }
        _approve(from, msg.sender, currentAllowance.sub(amount));
        _transfer(from, to, amount);
        return true;
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    function _transfer(address from, address to, uint256 amount) internal {
        if (to == address(0)) revert ZeroAddress();
        uint256 fromBalance = _balances[from];
        if (fromBalance < amount) {
            revert InsufficientBalance(from, amount, fromBalance);
        }
        _balances[from] = fromBalance.sub(amount);
        _balances[to] = _balances[to].add(amount);
        emit Transfer(from, to, amount);
    }

    function _approve(address owner, address spender, uint256 amount) internal {
        if (owner == address(0) || spender == address(0)) revert ZeroAddress();
        _allowances[owner][spender] = amount;
        emit Approval(owner, spender, amount);
    }

    function _mint(address account, uint256 amount) internal {
        if (account == address(0)) revert ZeroAddress();
        _totalSupply = _totalSupply.add(amount);
        _balances[account] = _balances[account].add(amount);
        emit Transfer(address(0), account, amount);
    }
}
