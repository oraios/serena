classdef Calculator < handle
    % Calculator A simple calculator class for testing MATLAB LSP
    %
    % This class provides basic arithmetic operations and demonstrates
    % MATLAB class structure for LSP testing purposes.

    properties
        LastResult double = 0
        History cell = {}
    end

    properties (Access = private)
        OperationCount uint32 = 0
    end

    methods
        function obj = Calculator()
            % Constructor for Calculator class
            obj.LastResult = 0;
            obj.History = {};
            obj.OperationCount = 0;
        end

        function result = add(obj, a, b)
            % ADD Add two numbers
            %   result = add(obj, a, b) returns the sum of a and b
            result = a + b;
            obj.updateState(result, 'add');
        end

        function result = subtract(obj, a, b)
            % SUBTRACT Subtract b from a
            %   result = subtract(obj, a, b) returns a - b
            result = a - b;
            obj.updateState(result, 'subtract');
        end

        function result = multiply(obj, a, b)
            % MULTIPLY Multiply two numbers
            %   result = multiply(obj, a, b) returns a * b
            result = a * b;
            obj.updateState(result, 'multiply');
        end

        function result = divide(obj, a, b)
            % DIVIDE Divide a by b
            %   result = divide(obj, a, b) returns a / b
            %   Throws error if b is zero
            if b == 0
                error('Calculator:DivisionByZero', 'Cannot divide by zero');
            end
            result = a / b;
            obj.updateState(result, 'divide');
        end

        function displayHistory(obj)
            % DISPLAYHISTORY Display the calculation history
            fprintf('Calculation History:\n');
            for i = 1:length(obj.History)
                fprintf('  %d: %s = %.4f\n', i, obj.History{i}.operation, obj.History{i}.result);
            end
        end
    end

    methods (Access = private)
        function updateState(obj, result, operation)
            % Update internal state after an operation
            obj.LastResult = result;
            obj.OperationCount = obj.OperationCount + 1;
            obj.History{end+1} = struct('operation', operation, 'result', result);
        end
    end

    methods (Static)
        function result = power(base, exponent)
            % POWER Compute base raised to exponent
            %   result = Calculator.power(base, exponent) returns base^exponent
            result = base ^ exponent;
        end
    end
end
