// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text;

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// Computes the Redis Cluster hash slot of a key, following the Redis Cluster specification:
/// CRC16 (XMODEM) of the hash tag (the text between the first '{' and the next '}', when it is not empty)
/// or of the whole key, modulo 16384.
/// </summary>
internal static class RedisHashSlot
{
    public static int Calculate(string key)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(key);
        ReadOnlySpan<byte> hashed = bytes;

        int open = Array.IndexOf(bytes, (byte)'{');
        if (open >= 0)
        {
            int close = Array.IndexOf(bytes, (byte)'}', open + 1);
            if (close > open + 1)
            {
                hashed = bytes.AsSpan(open + 1, close - open - 1);
            }
        }

        return Crc16(hashed) % 16384;
    }

    private static int Crc16(ReadOnlySpan<byte> data)
    {
        int crc = 0;
        foreach (byte b in data)
        {
            crc ^= b << 8;
            for (int i = 0; i < 8; i++)
            {
                crc = (crc & 0x8000) != 0 ? (crc << 1) ^ 0x1021 : crc << 1;
            }
        }

        return crc & 0xFFFF;
    }
}
