// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.
// See the LICENSE file in the project root for more information.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using BenchmarkDotNet.Running;
using System.IO;
using BenchmarkDotNet.Extensions;

namespace MicroBenchmarks
{
    class Program
    {
        static int Main(string[] args)
        {
            var argsList = new List<string>(args);
            int? partitionCount;
            int? partitionIndex;

            // Parse and remove any additional parameters that we need that aren't part of BDN
            try {
                argsList = ParseAndRemoveIntParameter(argsList, "--partition-count", out partitionCount);
                argsList = ParseAndRemoveIntParameter(argsList, "--partition-index", out partitionIndex);
            }

            catch (ArgumentException e)
            {
                Console.WriteLine("ArgumentException: {0}", e.Message);
                return 1;
            }

            return BenchmarkSwitcher
                .FromAssembly(typeof(Program).Assembly)
                .Run(argsList.ToArray(), RecommendedConfig.Create(
                    artifactsPath: new DirectoryInfo(Path.Combine(Path.GetDirectoryName(typeof(Program).Assembly.Location), "BenchmarkDotNet.Artifacts")), 
                    mandatoryCategories: ImmutableHashSet.Create(Categories.CoreFX, Categories.CoreCLR, Categories.ThirdParty),
                    partitionCount: partitionCount,
                    partitionIndex: partitionIndex))
                .ToExitCode();
        }

        // Find and parse given parameter with expected int value, then remove it and its value from the list of arguments to then pass to BenchmarkDotNet
        // Throws ArgumentException if the parameter does not have a value or that value is not parsable as an int
        public static List<string> ParseAndRemoveIntParameter(List<string> argsList, string parameter, out int? parameterValue)
        {
            int parameterIndex = argsList.IndexOf(parameter);
            parameterValue = null;

            if (parameterIndex != -1)
            {
                if (parameterIndex + 1 < argsList.Count && Int32.TryParse(argsList[parameterIndex+1], out int parsedParameterValue))
                {
                    // remove --partition-count args
                    parameterValue = parsedParameterValue;
                    argsList.RemoveAt(parameterIndex+1);
                    argsList.RemoveAt(parameterIndex);
                }
                else
                {
                    throw new ArgumentException(String.Format("{0} must be followed by an integer", parameter));
                }
            }

            return argsList;
        }
    }
}