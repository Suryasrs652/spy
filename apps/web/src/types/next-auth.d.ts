import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      email?: string | null;
      name?: string | null;
      image?: string | null;
    };
    organizationId: string;
    accessToken: string;
    emailVerified: boolean;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    userId?: string;
    organizationId?: string;
    accessToken?: string;
    refreshToken?: string;
    accessTokenExpiresAt?: number;
    emailVerified?: boolean;
  }
}
